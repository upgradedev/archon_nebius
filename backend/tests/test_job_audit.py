"""Unit tests for services/job_audit.py (the job_runs audit trail).

Best-effort by contract: a DB problem must never raise or block a submission, so
every failure path degrades to False / []. All DB access is mocked."""
from unittest.mock import MagicMock, patch

from services import job_audit


def _mock_conn(fetchall=None):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    if fetchall is not None:
        cur.fetchall.return_value = fetchall
        cur.description = [("job_id",), ("nebius_job_name",), ("job_type",),
                           ("period",), ("status",), ("submitted_by",),
                           ("submitted_email",), ("created_at",)]
    return conn, cur


# ── record_job_run ────────────────────────────────────────────────────────────

def test_record_no_job_id_returns_false():
    assert job_audit.record_job_run({}, "extraction", {"uid": "u"}) is False


def test_record_no_db_connection_returns_false():
    with patch("db.client.get_db_connection", side_effect=OSError("no db")):
        ok = job_audit.record_job_run({"id": "aijob-1"}, "analysis", {"uid": "u"})
    assert ok is False


def test_record_success_commits_and_passes_identity():
    conn, cur = _mock_conn()
    with patch("db.client.get_db_connection", return_value=conn):
        ok = job_audit.record_job_run(
            {"id": "aijob-1", "nebius_job_name": "archon-analysis-2026-01-x",
             "period": "2026-01", "status": "pending"},
            "analysis",
            {"uid": "uid-123", "email": "judge@x.com"},
        )
    assert ok is True
    conn.commit.assert_called_once()
    # The identity must reach the INSERT params.
    args = cur.execute.call_args[0][1]
    assert "uid-123" in args and "judge@x.com" in args


def test_record_never_raises_on_db_error():
    conn, cur = _mock_conn()
    cur.execute.side_effect = RuntimeError("boom")
    with patch("db.client.get_db_connection", return_value=conn):
        ok = job_audit.record_job_run({"id": "aijob-1"}, "extraction", None)
    assert ok is False
    conn.rollback.assert_called_once()


def test_record_tolerates_missing_identity():
    conn, _ = _mock_conn()
    with patch("db.client.get_db_connection", return_value=conn):
        assert job_audit.record_job_run({"id": "aijob-1"}, "extraction", None) is True


# ── list_recent_job_runs ──────────────────────────────────────────────────────

def test_list_no_db_returns_empty():
    with patch("db.client.get_db_connection", side_effect=OSError("no db")):
        assert job_audit.list_recent_job_runs() == []


def test_list_returns_rows_with_iso_dates():
    import datetime
    row = ("aijob-1", "name", "analysis", "2026-01", "pending",
           "uid-1", "e@x.com", datetime.datetime(2026, 7, 14, 10, 0, 0))
    conn, _ = _mock_conn(fetchall=[row])
    with patch("db.client.get_db_connection", return_value=conn):
        runs = job_audit.list_recent_job_runs(limit=10)
    assert len(runs) == 1
    assert runs[0]["job_id"] == "aijob-1"
    assert runs[0]["created_at"] == "2026-07-14T10:00:00"


def test_list_third_party_filter_builds_exclusion():
    conn, cur = _mock_conn(fetchall=[])
    with patch("db.client.get_db_connection", return_value=conn):
        job_audit.list_recent_job_runs(exclude_identities=["ci@archon.local"])
    sql = cur.execute.call_args[0][0]
    assert "ALL(" in sql  # the exclusion predicate was added


# ── GET /api/job-runs endpoint ────────────────────────────────────────────────

def test_job_runs_endpoint_degrades_gracefully(client):
    """No DB reachable → 200 with an empty list, never a 500."""
    with patch("db.client.get_db_connection", side_effect=OSError("no db")):
        resp = client.get("/api/job-runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == [] and body["count"] == 0


def test_job_runs_endpoint_third_party_filter(client):
    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return []

    with patch("services.job_audit.list_recent_job_runs", side_effect=fake_list):
        resp = client.get("/api/job-runs?third_party_only=true&since_hours=24")
    assert resp.status_code == 200
    assert resp.json()["third_party_only"] is True
    # our own accounts are excluded so only external (judge) activity remains
    assert captured["exclude_identities"] and "ci@archon.local" in captured["exclude_identities"]
    assert captured["since_hours"] == 24


def test_submit_records_audit_best_effort(client):
    """POST /jobs still returns the job even when the audit write fails."""
    fake_job = {"id": "aijob-x", "status": "pending", "period": "2026-01",
                "documentsCount": 0, "createdAt": "2026-07-14T00:00:00+00:00"}
    with patch("services.nebius.submit_extraction_job", return_value=fake_job), \
         patch("services.job_audit.record_job_run", return_value=False) as rec:
        resp = client.post("/api/jobs", json={"uploadId": "u1", "period": "2026-01"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "aijob-x"
    rec.assert_called_once()  # audit was attempted with the job + type
    assert rec.call_args[0][1] == "extraction"
