"""Offline CI coverage for scripts/verify_pg_mirror.py.

Drives the REAL verify() core with injected fakes (no live PG, no S3, no creds),
so the reproducibility verifier cannot silently rot. Exercises the shipped
pg_sync path indirectly via the same signature main() uses."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "verify_pg_mirror.py"

spec = importlib.util.spec_from_file_location("verify_pg_mirror", _SCRIPT)
vpm = importlib.util.module_from_spec(spec)
sys.modules["verify_pg_mirror"] = vpm
spec.loader.exec_module(vpm)


def _report(n_events=1, n_emp=1, n_val=1):
    return {
        "jobId": "j1",
        "report": {
            "period": "2026-03",
            "payrollEvents": [{"company_name": f"C{i}", "net_total": 1.0} for i in range(n_events)],
            "employeeSummaries": [{"employee_code": f"E{i}", "net_pay": 1.0} for i in range(n_emp)],
            "validationResults": [{"rule": f"R{i}", "passed": True} for i in range(n_val)],
        },
    }


def _deps(report, pg_counts, materialized=True):
    """Build (storage, pg_sync, get_db_connection) fakes.

    pg_counts is (payroll_events, employee_payroll, validation_results) as
    returned by the COUNT(*) queries in _pg_counts (called in order)."""
    storage = SimpleNamespace(
        download_json=lambda key: report,
        list_keys=lambda prefix: ["reports/2026-03/report.json"],
    )
    pg_sync = SimpleNamespace(materialize_report=lambda period, payload: materialized)

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [(c,) for c in pg_counts]
    get_db_connection = MagicMock(return_value=conn)
    return storage, pg_sync, get_db_connection


def test_pass_when_every_section_mirrors():
    storage, pg_sync, gdc = _deps(_report(1, 1, 1), pg_counts=(1, 1, 1))
    result = vpm.verify("2026-03", storage, pg_sync, gdc)
    assert result["ok"] is True
    assert all(r["ok"] for r in result["rows"])


def test_fail_when_a_section_is_empty_in_pg():
    # Report has a payroll event but PG stayed empty for payroll_events → MISMATCH.
    storage, pg_sync, gdc = _deps(_report(1, 1, 1), pg_counts=(0, 1, 1))
    result = vpm.verify("2026-03", storage, pg_sync, gdc)
    assert result["ok"] is False
    mism = [r for r in result["rows"] if not r["ok"]]
    assert len(mism) == 1 and mism[0]["label"] == "payroll events"


def test_pass_when_report_has_nothing_relational():
    # Pure-invoice period: no relational sections, PG empty → still PASS.
    storage, pg_sync, gdc = _deps(_report(0, 0, 0), pg_counts=(0, 0, 0), materialized=False)
    result = vpm.verify("2026-03", storage, pg_sync, gdc)
    assert result["ok"] is True


def test_main_returns_1_on_mismatch(monkeypatch, capsys):
    # Wire main()'s lazy imports to fakes, then assert exit code + output.
    storage, pg_sync, gdc = _deps(_report(1, 1, 1), pg_counts=(0, 0, 0))
    monkeypatch.setitem(sys.modules, "services", SimpleNamespace(storage=storage, pg_sync=pg_sync))
    monkeypatch.setitem(sys.modules, "services.storage", storage)
    monkeypatch.setitem(sys.modules, "services.pg_sync", pg_sync)
    monkeypatch.setitem(sys.modules, "db.client", SimpleNamespace(get_db_connection=gdc))
    monkeypatch.setitem(sys.modules, "db", SimpleNamespace(client=SimpleNamespace(get_db_connection=gdc)))

    rc = vpm.main(["verify_pg_mirror.py", "2026-03"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "MISMATCH" in out
    assert "FAIL" in out
