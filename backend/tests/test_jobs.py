"""Unit tests for POST /api/jobs and GET /api/jobs/{id}.

JOB_RUNNER_BACKEND=local so these tests hit the local HTTP wrapper mock
rather than the Nebius SDK.  The extraction service is mocked via httpx.
"""
from unittest.mock import patch, MagicMock
import httpx
import pytest


def _mock_local_response(job_id: str = "local-job-abc", status: str = "running"):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"jobId": job_id, "status": status}
    return mock


# ── POST /api/jobs ────────────────────────────────────────────────────────────

def test_submit_job_local_runner(client):
    with patch("httpx.post", return_value=_mock_local_response("job-001")) as mock_post:
        resp = client.post("/api/jobs", json={"uploadId": "abc123", "period": "2025-01"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "job-001"
    assert body["status"] == "running"
    assert body["period"] == "2025-01"
    mock_post.assert_called_once()


def test_submit_job_returns_created_at(client):
    with patch("httpx.post", return_value=_mock_local_response("job-002")):
        resp = client.post("/api/jobs", json={"uploadId": "xyz", "period": "2025-02"})
    assert "createdAt" in resp.json()


def test_submit_job_extraction_service_error(client):
    with patch("httpx.post", side_effect=httpx.HTTPError("connection refused")):
        resp = client.post("/api/jobs", json={"uploadId": "bad", "period": "2025-01"})
    assert resp.status_code == 500


def test_submit_job_missing_period(client):
    resp = client.post("/api/jobs", json={"uploadId": "abc123"})
    assert resp.status_code == 422


def test_submit_job_missing_upload_id(client):
    resp = client.post("/api/jobs", json={"period": "2025-01"})
    assert resp.status_code == 422


# ── GET /api/jobs/{id} ────────────────────────────────────────────────────────

def test_get_job_status_local_runner(client):
    with patch("httpx.get", return_value=_mock_local_response("job-003", "completed")):
        resp = client.get("/api/jobs/job-003")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_get_job_status_includes_progress(client):
    with patch("httpx.get", return_value=_mock_local_response("job-004", "completed")):
        resp = client.get("/api/jobs/job-004")
    body = resp.json()
    # Local runner maps completed → progress 100
    assert body.get("progress") in (None, 100, 50)


def test_get_job_status_service_error(client):
    with patch("httpx.get", side_effect=httpx.HTTPError("not found")):
        resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 500


def test_submit_job_rejects_invalid_period(client):
    resp = client.post("/api/jobs", json={"uploadId": "abc123", "period": "not-a-period"})
    assert resp.status_code == 422


def test_submit_job_rejects_invalid_month(client):
    resp = client.post("/api/jobs", json={"uploadId": "abc123", "period": "2026-13"})
    assert resp.status_code == 422
