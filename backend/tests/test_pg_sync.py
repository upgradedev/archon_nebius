"""Unit tests for backend/services/pg_sync.py — the best-effort materialization
of a completed report into the PostgreSQL read-model tables, and its wiring into
GET /api/reports/{period}.

All tests mock the DB connection (db.client.get_db_connection); no real
PostgreSQL is required — this is the CI-equivalent of the live write path."""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from main import app
from services import pg_sync


def _mock_conn():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    # employees INSERT ... RETURNING id
    cursor.fetchone.return_value = ("emp-uuid-1",)
    return conn, cursor


_REPORT = {
    "jobId": "job-123",
    "generatedAt": "2026-07-13T00:00:00Z",
    "report": {
        "period": "2026-03",
        "payrollEvents": [
            {
                "period": "2026-03",
                "company_name": "Acme SA",
                "net_total": 10000.0,
                "gross_total": 13000.0,
                "employer_cost_total": 17200.0,
                "employee_count": 3,
                "bank_confirmed": True,
                "validation_passed": True,
            }
        ],
        "employeeSummaries": [
            {
                "employee_code": "E001",
                "employee_name": "A. Papadopoulos",
                "period": "2026-03",
                "net_pay": 3300.0,
                "gross_pay": 4300.0,
                "employer_cost": 5700.0,
            }
        ],
        "validationResults": [
            {
                "rule": "R1: bank.total ~= sum(payslips) +/-2%",
                "passed": True,
                "severity": "info",
                "message": "reconciled",
                "source_files": ["extracted/2026-03/a/documents.json"],
            }
        ],
    },
}


def test_materialize_success_writes_all_tables_and_commits():
    conn, cur = _mock_conn()
    with patch("db.client.get_db_connection", return_value=conn):
        ok = pg_sync.materialize_report("2026-03", _REPORT)

    assert ok is True
    conn.commit.assert_called_once()
    sql = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    # Idempotent period clear
    assert "DELETE FROM validation_results" in sql
    assert "DELETE FROM employee_payroll" in sql
    assert "DELETE FROM payroll_events" in sql
    # All three never-previously-written tables get inserts
    assert "INSERT INTO validation_results" in sql
    assert "INSERT INTO payroll_events" in sql
    assert "INSERT INTO employees" in sql
    assert "INSERT INTO employee_payroll" in sql


def test_materialize_empty_report_is_noop_false():
    conn, cur = _mock_conn()
    with patch("db.client.get_db_connection", return_value=conn):
        ok = pg_sync.materialize_report("2026-03", {"report": {"period": "2026-03"}})
    assert ok is False
    conn.commit.assert_not_called()


def test_materialize_db_failure_rolls_back_and_returns_false():
    conn, cur = _mock_conn()
    cur.execute.side_effect = RuntimeError("connection reset")
    with patch("db.client.get_db_connection", return_value=conn):
        ok = pg_sync.materialize_report("2026-03", _REPORT)
    assert ok is False
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_materialize_no_db_connection_returns_false():
    with patch("db.client.get_db_connection", side_effect=ValueError("no DB configured")):
        ok = pg_sync.materialize_report("2026-03", _REPORT)
    assert ok is False


def test_employee_without_code_uses_synthetic_key():
    conn, cur = _mock_conn()
    payload = {
        "report": {
            "period": "2026-03",
            "employeeSummaries": [
                {"employee_code": None, "employee_name": "No Code", "period": "2026-03", "net_pay": 100.0}
            ],
        }
    }
    with patch("db.client.get_db_connection", return_value=conn):
        ok = pg_sync.materialize_report("2026-03", payload)
    assert ok is True
    # Synthetic key derived from period + name
    emp_insert = next(c for c in cur.execute.call_args_list if "INSERT INTO employees" in str(c.args[0]))
    assert emp_insert.args[1][0] == "2026-03:No Code"


def test_get_report_still_returns_when_materialize_raises():
    """Best-effort contract: a materialization blow-up must NOT break the read."""
    client = TestClient(app)
    with patch("services.storage.download_json", return_value=_REPORT), \
         patch("services.pg_sync.materialize_report", side_effect=RuntimeError("boom")):
        resp = client.get("/api/reports/2026-03")
    assert resp.status_code == 200
    assert resp.json()["jobId"] == "job-123"


def test_get_report_invokes_materialize():
    client = TestClient(app)
    with patch("services.storage.download_json", return_value=_REPORT), \
         patch("services.pg_sync.materialize_report") as m:
        resp = client.get("/api/reports/2026-03")
    assert resp.status_code == 200
    m.assert_called_once()
    assert m.call_args.args[0] == "2026-03"
