import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from services import storage

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class CompanyProfile(BaseModel):
    company_name: str = ""
    company_tax_id: str = ""


@router.get("/periods")
def list_periods():
    """List periods derived from PostgreSQL database or fallback S3 scanner, with extraction/report status."""
    # 1. Fetch report keys from S3 to determine hasReport status
    report_keys = storage.list_keys("reports/")
    report_periods = {
        k.split("/")[1]
        for k in report_keys
        if k.endswith("report.json") and len(k.split("/")) >= 3
    }

    # 2. Try to fetch periods from the PostgreSQL database
    db_periods = set()
    db_failed = False
    try:
        from db.client import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT period FROM documents")
                db_periods = {row[0] for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not list periods from PostgreSQL: %s — falling back to S3 bucket", exc)
        db_failed = True

    # 3. Fallback to S3 bucket scan if database failed
    if db_failed:
        raw_keys = storage.list_keys("raw-docs/")
        extracted_keys = storage.list_keys("extracted/")

        def _period_set(keys: list[str], prefix: str) -> set[str]:
            periods: set[str] = set()
            for key in keys:
                rest = key[len(prefix):]
                segment = rest.split("/")[0]
                if segment:
                    periods.add(segment)
            return periods

        raw_periods = _period_set(raw_keys, "raw-docs/")
        extracted_periods = _period_set(extracted_keys, "extracted/")

        all_periods = sorted(raw_periods | extracted_periods | report_periods, reverse=True)
        return [
            {
                "period": p,
                "hasReport": p in report_periods,
                "hasExtraction": p in extracted_periods,
            }
            for p in all_periods
        ]

    # 4. Otherwise, use strictly the DB periods combined with reports
    all_periods = sorted(db_periods | report_periods, reverse=True)
    return [
        {
            "period": p,
            "hasReport": p in report_periods,
            "hasExtraction": p in db_periods,
        }
        for p in all_periods
    ]


@router.delete("/periods/{period}")
def delete_period(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Delete all database and Object Storage data for a period."""
    # 1. Delete from PostgreSQL database
    try:
        from db.client import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM documents WHERE period = %s", (period,))
                cur.execute("DELETE FROM employee_payroll WHERE period = %s", (period,))
                cur.execute("DELETE FROM payroll_events WHERE period = %s", (period,))
                cur.execute("DELETE FROM validation_results WHERE period = %s", (period,))
            conn.commit()
            logger.info("Deleted period %s data from PostgreSQL", period)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not delete period %s from PostgreSQL: %s", period, exc)

    # 2. Delete from Object Storage
    count = storage.delete_prefix(f"raw-docs/{period}/")
    count += storage.delete_prefix(f"extracted/{period}/")
    count += storage.delete_prefix(f"reports/{period}/")
    return {"deleted": count, "period": period}


@router.get("/documents/{period}")
def get_documents(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Return all extracted documents for a period, as a flat list.

    Object Storage is the SOURCE OF TRUTH for extracted documents and is read
    FIRST. This matters: the extraction job writes a freshly-uploaded batch to S3
    but NOT to PostgreSQL (PG is a downstream mirror, populated only on review/report
    materialization). Reading PG first therefore returned a STALE list that hid a
    just-uploaded document — and because the review PUT deletes the per-upload S3
    originals, confirming that stale list permanently destroyed the new upload (the
    "I uploaded an invoice and it shows nowhere" data-loss bug). PostgreSQL is used
    only as a fallback when S3 has nothing.
    """
    # 1. Object Storage first (authoritative, always fresh). A genuine storage
    #    ERROR is surfaced as an error — never masked as "no documents" — so it can
    #    never silently hide data. Only a reachable-but-EMPTY S3 falls through to the
    #    PostgreSQL mirror below.
    try:
        keys = storage.list_keys(f"extracted/{period}/")
        doc_keys = sorted(k for k in keys if k.endswith("documents.json"))
        merged: list = []
        for key in doc_keys:
            payload = storage.download_json(key)
            docs = payload.get("documents", []) if isinstance(payload, dict) else payload
            if isinstance(docs, list):
                merged.extend(docs)
        if merged:
            return merged
    except ClientError as exc:
        logger.exception("Storage error listing documents for %s", period)
        raise HTTPException(status_code=502, detail="Storage error listing documents") from exc
    except Exception as exc:
        logger.exception("Document fetch failed for %s", period)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch documents: {type(exc).__name__}",
        ) from exc

    # 2. S3 was reachable but empty — fall back to the PostgreSQL mirror.
    try:
        from db.client import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        source_file, doc_type, detected_lang, issue_date,
                        vendor_name, vendor_tax_id, recipient_name, currency,
                        subtotal, vat_amount, vat_rate_pct, total_amount,
                        invoice_number, confidence, upload_id
                    FROM documents
                    WHERE period = %s
                    """,
                    (period,)
                )
                rows = cur.fetchall()
                if rows:
                    logger.info("S3 empty for %s; returning %d documents from PostgreSQL mirror",
                                period, len(rows))
                    return [{
                        "source_file": row[0], "doc_type": row[1],
                        "detected_language": row[2] or "en",
                        "issue_date": str(row[3]) if row[3] else None,
                        "vendor_name": row[4], "vendor_tax_id": row[5], "recipient_name": row[6],
                        "currency": row[7],
                        "subtotal": float(row[8]) if row[8] is not None else None,
                        "vat_amount": float(row[9]) if row[9] is not None else None,
                        "vat_rate_pct": float(row[10]) if row[10] is not None else None,
                        "total_amount": float(row[11]) if row[11] is not None else 0.0,
                        "invoice_number": row[12],
                        "confidence": float(row[13]) if row[13] is not None else 1.0,
                        "upload_id": row[14],
                    } for row in rows]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("PostgreSQL fallback for %s failed: %s", period, exc)

    raise HTTPException(status_code=404, detail=f"No extracted documents for period {period}")


class DocumentReviewRequest(BaseModel):
    # Kept intentionally permissive (raw dicts) so the reviewed payload round-trips
    # every extracted field — including sender/recipient and tax-id — without this
    # router needing to track the full extraction schema.
    documents: list[dict]


@router.put("/documents/{period}")
def update_documents(
    req: DocumentReviewRequest,
    period: str = Path(..., pattern=_PERIOD_PATTERN),
):
    """Persist the user-reviewed document set for a period to DB and S3."""
    # 1. Persist to PostgreSQL database
    db_saved = False
    try:
        from db.client import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Delete existing documents for the period
                cur.execute("DELETE FROM documents WHERE period = %s", (period,))
                
                # Insert the new reviewed documents
                for doc in req.documents:
                    # Sanitize dates / numbers
                    issue_date = doc.get("issue_date")
                    if not issue_date or issue_date == "—":
                        issue_date = None
                    
                    cur.execute(
                        """
                        INSERT INTO documents (
                            upload_id, period, source_file, doc_type, detected_lang,
                            issue_date, vendor_name, vendor_tax_id, recipient_name,
                            currency, subtotal, vat_amount, vat_rate_pct, total_amount,
                            invoice_number, confidence
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s
                        )
                        """,
                        (
                            doc.get("upload_id") or "reviewed",
                            period,
                            doc.get("source_file") or doc.get("filename") or "file",
                            doc.get("doc_type", "unknown"),
                            doc.get("detected_language") or doc.get("detected_lang") or "en",
                            issue_date,
                            doc.get("vendor_name"),
                            doc.get("vendor_tax_id"),
                            doc.get("recipient_name"),
                            doc.get("currency") or "EUR",
                            doc.get("subtotal"),
                            doc.get("vat_amount"),
                            doc.get("vat_rate_pct"),
                            doc.get("total_amount") or 0.0,
                            doc.get("invoice_number"),
                            doc.get("confidence") if doc.get("confidence") is not None else 1.0
                        )
                    )
                conn.commit()
                db_saved = True
                logger.info("Saved %d reviewed documents to PostgreSQL for period %s", len(req.documents), period)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not save reviewed documents for %s to PostgreSQL: %s", period, exc)

    # 2. Persist to Object Storage
    reviewed_key = f"extracted/{period}/reviewed/documents.json"
    try:
        originals = [
            k
            for k in storage.list_keys(f"extracted/{period}/")
            if k.endswith("documents.json") and k != reviewed_key
        ]
        storage.put_json(
            reviewed_key,
            {"period": period, "upload_id": "reviewed", "documents": req.documents},
        )
        deleted = 0
        for key in originals:
            storage.delete_key(key)
            deleted += 1
        return {"period": period, "documents": len(req.documents), "deleted": deleted}
    except ClientError as exc:
        logger.exception("Storage error saving documents for %s", period)
        raise HTTPException(status_code=502, detail="Storage error saving documents") from exc
    except Exception as exc:
        logger.exception("Document save failed for %s", period)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save documents: {type(exc).__name__}",
        ) from exc


@router.get("/company-profile")
def get_company_profile():
    """Return company profile from Object Storage (empty object if not set yet)."""
    try:
        return storage.download_json("company/profile.json")
    except ClientError:
        return {"company_name": "", "company_tax_id": ""}
    except Exception as exc:
        logger.exception("Company profile fetch failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch company profile: {type(exc).__name__}",
        ) from exc


@router.put("/company-profile")
def update_company_profile(profile: CompanyProfile):
    """Persist company profile to Object Storage."""
    try:
        storage.put_json("company/profile.json", profile.model_dump())
        return profile
    except Exception as exc:
        logger.exception("Company profile save failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save company profile: {type(exc).__name__}",
        ) from exc
