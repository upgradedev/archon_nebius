"""
Archon — Document Extraction Job
Runs as a Nebius Serverless AI Job (batch).

Entry point: reads UPLOAD_ID and PERIOD from env,
downloads raw documents from object storage,
routes each file through the appropriate extractor,
writes structured JSON results back to storage.
"""

import os
import json
import tempfile
import logging
from pathlib import Path

import boto3
from botocore.config import Config

from extractors.image import ImageExtractor
from extractors.pdf import PdfExtractor
from extractors.docx import DocxExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("archon.extraction")

UPLOAD_ID = os.environ["UPLOAD_ID"]
PERIOD = os.environ["PERIOD"]
BUCKET = os.environ["NEBIUS_BUCKET_NAME"]

EXTRACTORS = [PdfExtractor(), DocxExtractor(), ImageExtractor()]


def s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("STORAGE_ENDPOINT_URL"),
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.getenv("NEBIUS_REGION", "eu-north1"),
        config=Config(signature_version="s3v4"),
    )


def list_raw_files() -> list[str]:
    prefix = f"raw-docs/{PERIOD}/{UPLOAD_ID}/"
    paginator = s3().get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if not k.endswith("manifest.json"):
                keys.append(k)
    return keys


def download(key: str, dest: Path) -> None:
    s3().download_file(BUCKET, key, str(dest))


def upload_result(key: str, data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    s3().put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")


def process_file(key: str) -> dict | None:
    filename = key.split("/")[-1]
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        download(key, tmp_path)
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


def main():
    log.info("Starting extraction job — upload=%s period=%s", UPLOAD_ID, PERIOD)
    raw_keys = list_raw_files()
    log.info("Found %d files to process", len(raw_keys))

    results = []
    for key in raw_keys:
        result = process_file(key)
        if result:
            results.append(result)

    # Write aggregated extraction output
    output_key = f"extracted/{PERIOD}/{UPLOAD_ID}/documents.json"
    upload_result(output_key, {"period": PERIOD, "upload_id": UPLOAD_ID, "documents": results})
    log.info("Wrote %d extracted documents to %s", len(results), output_key)


if __name__ == "__main__":
    main()
