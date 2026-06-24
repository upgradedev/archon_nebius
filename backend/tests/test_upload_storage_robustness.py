"""Regression tests for the /upload 500 (storage region misconfig) + period UX.

The prod 500 happened because storage signed S3 requests for the wrong region
(default ``eu-north1`` vs the deployed ``eu-west1`` endpoint), and the upload
endpoint let any storage error surface as a bare 500. These tests pin: the
region resolution, filename-based period auto-detection, and that storage
failures now return a clear 502 — the layer the previous (storage-mocked) tests
never covered.
"""
from unittest.mock import patch

from routers.upload import _detect_period
from services import storage


# --- storage signing region (the actual root cause) -----------------------
def test_region_explicit_env_wins(monkeypatch):
    monkeypatch.setenv("NEBIUS_REGION", "eu-north1")
    assert storage._region() == "eu-north1"


def test_region_derived_from_endpoint(monkeypatch):
    monkeypatch.delenv("NEBIUS_REGION", raising=False)
    monkeypatch.setenv("STORAGE_ENDPOINT_URL", "https://storage.eu-west1.nebius.cloud")
    assert storage._region() == "eu-west1"


def test_region_default_is_not_eu_north1(monkeypatch):
    # The bug: defaulting to eu-north1 broke SigV4 against the eu-west1 endpoint.
    monkeypatch.delenv("NEBIUS_REGION", raising=False)
    monkeypatch.setenv("STORAGE_ENDPOINT_URL", "http://localstack:4566")
    assert storage._region() == "eu-west1"


# --- period auto-detection (no manual selection needed) -------------------
def test_detect_period_from_filenames():
    assert _detect_period(["anthropic_invoice_202601.pdf", "bank_202601.pdf"]) == "2026-01"
    assert _detect_period(["report_2026-03.pdf"]) == "2026-03"
    assert _detect_period(["no_date_here.pdf"]) is None


# --- endpoint behaviour ---------------------------------------------------
def _files(name="anthropic_invoice_202601.pdf"):
    return [("files", (name, b"%PDF-1.4 mock", "application/pdf"))]


def test_upload_autodetects_period_when_omitted(client):
    with patch("services.storage.upload_file", return_value="ok"), \
         patch("services.storage.put_json", return_value="ok"):
        resp = client.post("/api/upload", files=_files())  # NB: no period field
    assert resp.status_code == 200, resp.text
    assert resp.json()["period"] == "2026-01"


def test_upload_storage_failure_returns_502_not_500(client):
    with patch("services.storage.upload_file", side_effect=RuntimeError("SignatureDoesNotMatch")), \
         patch("services.storage.put_json", return_value="ok"):
        resp = client.post("/api/upload", files=_files())
    assert resp.status_code == 502, resp.text
    assert "Storage upload failed" in resp.json()["detail"]
