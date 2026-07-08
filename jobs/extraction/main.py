"""
Archon — Document Extraction Job
Runs as a Nebius Serverless AI Job (batch).

Pipeline (single-responsibility agents in sequence):
  1. ExtractorAgent  — auto-detect file type, call vision/text LLM, produce ExtractedDocument
  2. ClassifierAgent — rule-based refinement of doc_type (no LLM, deterministic)
  3. EventLinkerAgent — group payroll docs into unified PayrollEvents
  4. ValidatorAgent  — cross-document consistency rules, produce ValidationResults

Outputs written to Nebius Object Storage:
  extracted/{period}/{upload_id}/documents.json
  extracted/{period}/{upload_id}/events.json
  extracted/{period}/{upload_id}/validation.json
"""

import json
import logging
import os
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config

from agents import classifier, event_linker, validator
from extractors.image import ImageExtractor
from extractors.pdf import PdfExtractor
from extractors.docx import DocxExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("archon.extraction")

BUCKET = os.environ["NEBIUS_BUCKET_NAME"]

EXTRACTORS = [PdfExtractor(), DocxExtractor(), ImageExtractor()]


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("STORAGE_ENDPOINT_URL"),
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.getenv("NEBIUS_REGION", "eu-west1"),
        config=Config(signature_version="s3v4"),
    )


def _list_raw_files(upload_id: str, period: str) -> list[str]:
    prefix = f"raw-docs/{period}/{upload_id}/"
    paginator = _s3().get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if not k.endswith("manifest.json"):
                keys.append(k)
    return keys


def _download(key: str, dest: Path) -> None:
    _s3().download_file(BUCKET, key, str(dest))


def _put_json(key: str, data: object) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    _s3().put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")


# ── extractor step ────────────────────────────────────────────────────────────

def _extract_file(key: str) -> dict | None:
    filename = key.split("/")[-1]
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        _download(key, tmp_path)
        extractor = next((e for e in EXTRACTORS if e.can_handle(tmp_path)), None)
        if extractor is None:
            log.warning("No extractor for %s — skipping", filename)
            return None
        log.info("Extracting %s with %s", filename, type(extractor).__name__)
        doc = extractor.extract(tmp_path)
        return doc.model_dump()
    except Exception as exc:
        log.error("Failed to extract %s: %s", filename, exc)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


# ── main pipeline ─────────────────────────────────────────────────────────────

def main(upload_id: str | None = None, period: str | None = None):
    # ADR-008: accept params so concurrent local-dev jobs do not race on
    # process-level env; fall back to env for the production Nebius Job path.
    upload_id = upload_id or os.environ["UPLOAD_ID"]
    period = period or os.environ["PERIOD"]
    log.info("=== Extraction job start — upload=%s period=%s ===", upload_id, period)

    # Step 1: extract raw files
    raw_keys = _list_raw_files(upload_id, period)
    log.info("Found %d files to process", len(raw_keys))
    raw_docs = [r for k in raw_keys if (r := _extract_file(k)) is not None]
    log.info("Extracted %d documents", len(raw_docs))

    # Deserialise into typed models for the agent pipeline
    from models.document import ExtractedDocument
    typed_docs = []
    for d in raw_docs:
        try:
            typed_docs.append(ExtractedDocument(**d))
        except Exception as exc:
            log.warning("Skipping malformed extraction result: %s", exc)

    # Step 2: classify (rule-based, no LLM)
    typed_docs = classifier.run(typed_docs)
    log.info("Classification complete")

    # Step 2b: advisory prompt-injection scan over each document's extracted
    # fields. Pure/deterministic, no LLM. The extractors' DATA-not-instructions
    # fence already neutralized any injected directive; this only SURFACES what
    # was captured-as-data so the validation output can show it. Never rejects.
    from injection_scan import scan_document
    injection_flagged = 0
    injection_hits = 0
    for d in typed_docs:
        result = scan_document(d.model_dump())
        d.injection_scan = result.as_dict()
        if result.detected:
            injection_flagged += 1
            injection_hits += result.count
            log.warning(
                "Prompt-injection patterns in %s: %d hit(s) — captured as data, not followed",
                d.source_file, result.count,
            )
    log.info("Injection scan: %d/%d documents flagged (%d hits)",
             injection_flagged, len(typed_docs), injection_hits)

    # Step 3: link payroll events
    events = event_linker.run(typed_docs)
    log.info("Linked %d payroll events", len(events))

    # Step 4: validate cross-document consistency
    validation_results = validator.run(events)
    errors = sum(1 for r in validation_results if not r.passed and r.severity == "error")
    log.info("Validation: %d results, %d errors", len(validation_results), errors)

    # Write outputs
    base = f"extracted/{period}/{upload_id}"

    _put_json(f"{base}/documents.json", {
        "period": period,
        "upload_id": upload_id,
        "documents": [d.model_dump() for d in typed_docs],
    })

    _put_json(f"{base}/events.json", {
        "period": period,
        "upload_id": upload_id,
        "events": [e.model_dump() for e in events],
    })

    _put_json(f"{base}/validation.json", {
        "period": period,
        "upload_id": upload_id,
        "results": [r.model_dump() for r in validation_results],
        "summary": {
            "total": len(validation_results),
            "passed": sum(1 for r in validation_results if r.passed),
            "errors": errors,
            "warnings": sum(1 for r in validation_results if not r.passed and r.severity == "warning"),
        },
        # Advisory prompt-injection visibility — aggregate + per-document detail.
        # documents_flagged/total_hits summarise; documents lists each source file
        # with its scan so the dashboard/report can badge "prompt-injection scanned".
        "injection_scan": {
            "documents_flagged": injection_flagged,
            "total_hits": injection_hits,
            "documents": [
                {"source_file": d.source_file, **(d.injection_scan or {})}
                for d in typed_docs
            ],
        },
    })

    log.info("=== Extraction job complete — %d docs, %d events ===", len(typed_docs), len(events))


if __name__ == "__main__":
    main()
