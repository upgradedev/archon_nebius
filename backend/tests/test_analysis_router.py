"""Unit tests for /api/analyze and /api/reports/{period} endpoints.

All Nebius SDK calls and storage calls are mocked.
JOB_RUNNER_BACKEND=local (from conftest) so analysis router hits
the local HTTP wrapper path; individual tests that need the Nebius
SDK path patch submit_analysis_job directly.
"""
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError


# ── POST /api/analyze ─────────────────────────────────────────────────────────

def _analysis_job_result(job_id: str = "ajob-001", period: str = "2025-01") -> dict:
    return {
        "id": job_id,
        "status": "pending",
        "period": period,
        "documentsCount": 0,
        "createdAt": "2025-01-01T00:00:00+00:00",
    }


def test_trigger_analysis_returns_job_id(client):
    with patch("services.nebius.submit_analysis_job", return_value=_analysis_job_result()):
        resp = client.post("/api/analyze", json={"period": "2025-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "ajob-001"
    assert body["status"] == "pending"


def test_trigger_analysis_returns_period(client):
    with patch("services.nebius.submit_analysis_job", return_value=_analysis_job_result("ajob-002", "2025-06")):
        resp = client.post("/api/analyze", json={"period": "2025-06"})
    assert resp.json()["period"] == "2025-06"


def test_trigger_analysis_rejects_invalid_period_format(client):
    resp = client.post("/api/analyze", json={"period": "january-2025"})
    assert resp.status_code == 422


def test_trigger_analysis_rejects_invalid_month(client):
    resp = client.post("/api/analyze", json={"period": "2025-13"})
    assert resp.status_code == 422


def test_trigger_analysis_rejects_month_zero(client):
    resp = client.post("/api/analyze", json={"period": "2025-00"})
    assert resp.status_code == 422


def test_trigger_analysis_missing_period(client):
    resp = client.post("/api/analyze", json={})
    assert resp.status_code == 422


def test_trigger_analysis_sdk_error_returns_500(client):
    with patch("services.nebius.submit_analysis_job", side_effect=RuntimeError("SDK unavailable")):
        resp = client.post("/api/analyze", json={"period": "2025-01"})
    assert resp.status_code == 500
    assert "Failed to submit" in resp.json()["detail"]


def test_trigger_analysis_returns_created_at(client):
    with patch("services.nebius.submit_analysis_job", return_value=_analysis_job_result()):
        resp = client.post("/api/analyze", json={"period": "2025-01"})
    assert "createdAt" in resp.json()


# ── GET /api/analyze/{job_id} ─────────────────────────────────────────────────

def test_get_analysis_status_running(client):
    with patch("services.nebius.get_job_status", return_value={"id": "ajob-001", "status": "running"}):
        resp = client.get("/api/analyze/ajob-001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_get_analysis_status_completed(client):
    with patch("services.nebius.get_job_status", return_value={"id": "ajob-002", "status": "completed"}):
        resp = client.get("/api/analyze/ajob-002")
    assert resp.json()["status"] == "completed"


def test_get_analysis_status_error_returns_500(client):
    with patch("services.nebius.get_job_status", side_effect=Exception("poll error")):
        resp = client.get("/api/analyze/missing-job")
    assert resp.status_code == 500


# ── GET /api/reports/{period} ─────────────────────────────────────────────────

_SAMPLE_REPORT = {
    "period": "2025-01",
    "pnl": {"revenue": 100000, "total_cost": 75000, "net_profit": 25000},
    "summary": "Strong month.",
}


def test_get_report_returns_json(client):
    with patch("services.storage.download_json", return_value=_SAMPLE_REPORT):
        resp = client.get("/api/reports/2025-01")
    assert resp.status_code == 200
    assert resp.json()["period"] == "2025-01"


def test_get_report_not_found_returns_404(client):
    err = ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")
    with patch("services.storage.download_json", side_effect=err):
        resp = client.get("/api/reports/2025-02")
    assert resp.status_code == 404
    assert "2025-02" in resp.json()["detail"]


def test_get_report_storage_error_returns_502(client):
    err = ClientError({"Error": {"Code": "503", "Message": "unavailable"}}, "GetObject")
    with patch("services.storage.download_json", side_effect=err):
        resp = client.get("/api/reports/2025-03")
    assert resp.status_code == 502


def test_get_report_invalid_period_format_returns_422(client):
    resp = client.get("/api/reports/bad-period")
    assert resp.status_code == 422


def test_get_report_invalid_month_returns_422(client):
    resp = client.get("/api/reports/2025-13")
    assert resp.status_code == 422


def test_get_report_generic_error_returns_500(client):
    with patch("services.storage.download_json", side_effect=Exception("unknown error")):
        resp = client.get("/api/reports/2025-04")
    assert resp.status_code == 500
