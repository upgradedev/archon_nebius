"""Stage 1 — input validation at the API edge (no LLM, deterministic).

These exhaustively exercise the guardrails on /api/upload, /api/jobs and
/api/analyze so a bad request can never reach the pipeline.
"""
import io

import pytest

PDF = b"%PDF-1.4 e2e validation probe"


def _pdf(name):
    return ("files", (name, io.BytesIO(PDF), "application/pdf"))


def test_upload_rejects_no_files(http, base_url, period):
    r = http.post(f"{base_url}/api/upload", data={"period": period}, timeout=30)
    assert r.status_code in (400, 422), r.text


def test_upload_rejects_unsupported_extension(http, base_url, period):
    files = [("files", ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream"))]
    r = http.post(f"{base_url}/api/upload", data={"period": period}, files=files, timeout=30)
    assert r.status_code == 400
    assert "Unsupported" in r.json().get("detail", "")


@pytest.mark.parametrize("bad_period", ["2026-13", "2026-00", "january", "../admin", "26-01", "2026/01"])
def test_upload_rejects_invalid_period(http, base_url, bad_period):
    r = http.post(f"{base_url}/api/upload", data={"period": bad_period}, files=[_pdf("a.pdf")], timeout=30)
    assert r.status_code == 422, f"{bad_period} -> {r.status_code}"


def test_upload_rejects_too_many_files(http, base_url, period):
    files = [_pdf(f"f{i}.pdf") for i in range(51)]
    r = http.post(f"{base_url}/api/upload", data={"period": period}, files=files, timeout=60)
    assert r.status_code == 400
    assert "50" in r.json().get("detail", "")


def test_upload_sanitizes_path_traversal_filename(http, base_url, period):
    files = [("files", ("../../etc/passwd.pdf", io.BytesIO(PDF), "application/pdf"))]
    r = http.post(f"{base_url}/api/upload", data={"period": period}, files=files, timeout=30)
    assert r.status_code == 200
    returned = r.json()["files"][0]["filename"]
    assert ".." not in returned and "/" not in returned


@pytest.mark.parametrize("bad_period", ["2026-13", "not-a-period", "../x"])
def test_jobs_rejects_invalid_period(http, base_url, bad_period):
    r = http.post(f"{base_url}/api/jobs", json={"uploadId": "x", "period": bad_period}, timeout=30)
    assert r.status_code == 422


def test_jobs_rejects_missing_fields(http, base_url):
    assert http.post(f"{base_url}/api/jobs", json={"period": "2026-01"}, timeout=30).status_code == 422
    assert http.post(f"{base_url}/api/jobs", json={"uploadId": "x"}, timeout=30).status_code == 422


@pytest.mark.parametrize("bad_period", ["2026-13", "january", "../admin"])
def test_analyze_rejects_invalid_period(http, base_url, bad_period):
    r = http.post(f"{base_url}/api/analyze", json={"period": bad_period}, timeout=30)
    assert r.status_code == 422


def test_reports_unknown_period_is_404(http, base_url):
    r = http.get(f"{base_url}/api/reports/2009-09", timeout=30)
    assert r.status_code == 404


def test_documents_unknown_period_is_404(http, base_url):
    r = http.get(f"{base_url}/api/documents/2009-09", timeout=30)
    assert r.status_code == 404
