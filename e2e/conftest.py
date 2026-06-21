"""Shared fixtures for the exhaustive end-to-end pipeline tests.

These run against a LIVE Archon stack (backend + extraction + analysis +
localstack) started via `docker compose up`. They drive the real REST API and
the real Nebius Inference API (vision + analysis models), then assert on every
stage of the pipeline: upload -> extract -> link -> validate -> analyze ->
report -> dashboard endpoints.

Config via env:
  BACKEND_URL        backend base url (default http://localhost:8000)
  STORAGE_ENDPOINT_URL  localstack S3 endpoint (default http://localhost:4566)
  NEBIUS_BUCKET_NAME    bucket name (default archon-bucket)
  E2E_PERIOD         period to use (default 2026-01)
  E2E_EXTRACT_TIMEOUT_S  max seconds to wait for extraction (default 420)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
STORAGE_ENDPOINT = os.environ.get("STORAGE_ENDPOINT_URL", "http://localhost:4566")
BUCKET = os.environ.get("NEBIUS_BUCKET_NAME", "archon-bucket")
PERIOD = os.environ.get("E2E_PERIOD", "2026-01")
EXTRACT_TIMEOUT_S = int(os.environ.get("E2E_EXTRACT_TIMEOUT_S", "420"))

REPO_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_DIR / "sample-data"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def period() -> str:
    return PERIOD


@pytest.fixture(scope="session")
def http() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(scope="session")
def sample_pdfs() -> list[Path]:
    pdfs = sorted(SAMPLE_DIR.rglob("*.pdf"))
    if not pdfs:
        pytest.skip(f"No sample PDFs under {SAMPLE_DIR} — run scripts/generate-sample-data.py")
    return pdfs


@pytest.fixture(scope="session")
def s3():
    """Optional boto3 client against localstack for storage-layer assertions.

    Returns None if boto3 / localstack isn't reachable, so storage assertions
    degrade to skips rather than hard-failing the whole suite.
    """
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=STORAGE_ENDPOINT,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
            region_name=os.environ.get("NEBIUS_REGION", "us-east-1"),
            config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
        )
        client.list_buckets()
        return client
    except Exception:
        return None


def _list_keys(s3, prefix: str) -> list[str]:
    keys: list[str] = []
    token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        keys += [o["Key"] for o in resp.get("Contents", [])]
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


@pytest.fixture(scope="session")
def list_keys():
    return _list_keys


def _poll_job(http: requests.Session, base_url: str, job_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        r = http.get(f"{base_url}/api/jobs/{job_id}", timeout=30)
        r.raise_for_status()
        last = r.json()
        status = last.get("status")
        if status == "completed":
            return last
        if status == "failed":
            raise AssertionError(f"Extraction job {job_id} FAILED: {last}")
        time.sleep(5)
    raise AssertionError(f"Extraction job {job_id} did not complete within {timeout_s}s (last={last})")


@pytest.fixture(scope="session")
def completed_pipeline(http, base_url, period, sample_pdfs):
    """Run the full pipeline ONCE for the session and return its artifacts.

    upload -> submit extraction -> poll to completed -> trigger analysis.
    Expensive (real LLM calls), so it's session-scoped and shared across the
    assertion test modules.
    """
    # Clean any prior data for an idempotent run.
    http.delete(f"{base_url}/api/periods/{period}", timeout=60)

    # 1. Upload all sample PDFs.
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in sample_pdfs]
    up = http.post(f"{base_url}/api/upload", data={"period": period}, files=files, timeout=120)
    up.raise_for_status()
    upload = up.json()

    # 2. Submit extraction job.
    job = http.post(
        f"{base_url}/api/jobs",
        json={"uploadId": upload["uploadId"], "period": period},
        timeout=60,
    )
    job.raise_for_status()
    job_data = job.json()
    job_id = job_data.get("id") or job_data.get("jobId")

    # 3. Poll extraction to completion.
    final_job = _poll_job(http, base_url, job_id, EXTRACT_TIMEOUT_S)

    # 4. Read extracted documents.
    docs_resp = http.get(f"{base_url}/api/documents/{period}", timeout=60)
    documents = docs_resp.json() if docs_resp.status_code == 200 else None

    # 5. Trigger analysis (synchronous in local mode).
    an = http.post(f"{base_url}/api/analyze", json={"period": period}, timeout=180)
    an.raise_for_status()
    analysis = an.json()

    # 6. Fetch the report. The endpoint returns an envelope
    #    {jobId, report: {<FinancialReport>}, generatedAt}; unwrap to the report.
    rep = http.get(f"{base_url}/api/reports/{period}", timeout=60)
    report = None
    if rep.status_code == 200:
        envelope = rep.json()
        report = envelope.get("report", envelope) if isinstance(envelope, dict) else envelope

    return {
        "upload": upload,
        "job": final_job,
        "documents": documents,
        "analysis": analysis,
        "report": report,
        "n_uploaded": len(sample_pdfs),
        "period": period,
    }
