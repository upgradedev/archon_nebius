from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from services import storage

router = APIRouter()

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class CompanyProfile(BaseModel):
    company_name: str = ""
    company_tax_id: str = ""


@router.get("/periods")
def list_periods():
    """List periods derived from uploaded raw-docs, with extraction/report status."""
    raw_keys = storage.list_keys("raw-docs/")
    extracted_keys = storage.list_keys("extracted/")
    report_keys = storage.list_keys("reports/")

    def _period_set(keys: list[str], prefix: str) -> set[str]:
        periods: set[str] = set()
        for key in keys:
            # key = "{prefix}/{period}/..."
            rest = key[len(prefix):]
            segment = rest.split("/")[0]
            if segment:
                periods.add(segment)
        return periods

    raw_periods = _period_set(raw_keys, "raw-docs/")
    extracted_periods = _period_set(extracted_keys, "extracted/")
    report_periods = {
        k.split("/")[1]
        for k in report_keys
        if k.endswith("report.json") and len(k.split("/")) >= 3
    }

    all_periods = sorted(raw_periods | extracted_periods | report_periods, reverse=True)
    return [
        {
            "period": p,
            "hasReport": p in report_periods,
            "hasExtraction": p in extracted_periods,
        }
        for p in all_periods
    ]


@router.delete("/periods/{period}")
def delete_period(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Delete all Object Storage data for a period."""
    count = storage.delete_prefix(f"raw-docs/{period}/")
    count += storage.delete_prefix(f"extracted/{period}/")
    count += storage.delete_prefix(f"reports/{period}/")
    return {"deleted": count, "period": period}


@router.get("/documents/{period}")
def get_documents(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Return all extracted documents for a period, as a flat list.

    Extraction writes one file per upload batch at
    ``extracted/{period}/{upload_id}/documents.json`` (shape:
    ``{period, upload_id, documents: [...]}``). We aggregate across all batches
    — mirroring the analysis loader — and return the merged ``documents`` list,
    which is what the frontend (and the analysis pipeline) expect.
    """
    try:
        keys = storage.list_keys(f"extracted/{period}/")
        doc_keys = sorted(k for k in keys if k.endswith("documents.json"))
        if not doc_keys:
            raise HTTPException(
                status_code=404,
                detail=f"No extracted documents for period {period}",
            )
        merged: list = []
        for key in doc_keys:
            payload = storage.download_json(key)
            docs = payload.get("documents", []) if isinstance(payload, dict) else payload
            if isinstance(docs, list):
                merged.extend(docs)
        return merged
    except HTTPException:
        raise
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/company-profile")
def get_company_profile():
    """Return company profile from Object Storage (empty object if not set yet)."""
    try:
        return storage.download_json("company/profile.json")
    except ClientError:
        return {"company_name": "", "company_tax_id": ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/company-profile")
def update_company_profile(profile: CompanyProfile):
    """Persist company profile to Object Storage."""
    try:
        storage.put_json("company/profile.json", profile.model_dump())
        return profile
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
