#!/usr/bin/env python3
"""
Verify the PostgreSQL read-model mirror end-to-end (see ADR on the PG mirror +
backend/services/pg_sync.py).

What it proves
--------------
On a normal pipeline run the analysis Job writes only Object Storage; the
backend mirrors the completed report into the relational tables best-effort on
`GET /reports/{period}`. This script runs that EXACT code path
(`pg_sync.materialize_report`, the shipped function — not a reimplementation)
against a live period and asserts the tables actually populated:

    reports/{period}/report.json  ──(pg_sync)──▶  payroll_events
                                                  employee_payroll
                                                  validation_results

PASS means: for every relational section the report contained, the matching PG
table now holds rows for that period (and an empty section stays empty).

Why this is a SCRIPT, not a CI test
-----------------------------------
The Managed PostgreSQL cluster is IP-allowlisted and needs real credentials, so
this cannot run in CI (which has no reachable PG). It is a one-command
reproducibility check meant to run from an AUTHORIZED environment: the backend
Endpoint, a CI job holding the prod secrets, or your own allowlisted machine.
Credentials come from the environment only (DATABASE_URL / POSTGRES_* + the
storage keys backend/services/storage.py reads).

Usage
-----
    # from repos/nebius
    python scripts/verify_pg_mirror.py [PERIOD]

    PERIOD is YYYY-MM. If omitted, the newest period that has a report is used.
    Exit code 0 = PASS, non-zero = FAIL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Run the real backend code paths: put backend/ on sys.path exactly as the
# service does (its modules import as `services.*` / `db.*`).
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_SECTIONS = [
    # (report key, PG table, human label)
    ("payrollEvents", "payroll_events", "payroll events"),
    ("employeeSummaries", "employee_payroll", "employee payroll lines"),
    ("validationResults", "validation_results", "validation results"),
]


def _apply_schema(get_db_connection) -> None:
    """Idempotent CREATE TABLE IF NOT EXISTS ... — safe to run every time."""
    schema = (_BACKEND / "db" / "schema.sql").read_text(encoding="utf-8")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()
    finally:
        conn.close()


def _pg_counts(get_db_connection, period: str) -> dict:
    """Row count per mirrored table for `period`."""
    conn = get_db_connection()
    counts = {}
    try:
        with conn.cursor() as cur:
            for _, table, _ in _SECTIONS:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE period = %s", (period,))
                counts[table] = int(cur.fetchone()[0])
    finally:
        conn.close()
    return counts


def _newest_period_with_report(storage) -> str | None:
    keys = storage.list_keys("reports/")
    periods = sorted(
        {k.split("/")[1] for k in keys if k.endswith("report.json") and len(k.split("/")) >= 3}
    )
    return periods[-1] if periods else None


def verify(period: str, storage, pg_sync, get_db_connection) -> dict:
    """Core, dependency-injected so it is unit-testable without live infra.

    Returns a result dict: {period, expected, actual, materialized, rows}.
    `rows` is a per-section list of {label, report_count, pg_count, ok}.
    """
    _apply_schema(get_db_connection)

    payload = storage.download_json(f"reports/{period}/report.json")
    report = payload.get("report", payload) if isinstance(payload, dict) else {}
    expected = {rk: len(report.get(rk) or []) for rk, _, _ in _SECTIONS}

    materialized = pg_sync.materialize_report(period, payload)

    counts = _pg_counts(get_db_connection, period)

    rows = []
    ok_all = True
    for rk, table, label in _SECTIONS:
        rc = expected[rk]
        pc = counts.get(table, 0)
        # Meaningful check: something in the report → rows in PG; nothing → nothing.
        ok = (rc == 0 and pc == 0) or (rc > 0 and pc > 0)
        ok_all = ok_all and ok
        rows.append({"label": label, "report_count": rc, "pg_count": pc, "ok": ok})

    return {
        "period": period,
        "expected": expected,
        "actual": counts,
        "materialized": materialized,
        "rows": rows,
        "ok": ok_all,
    }


def main(argv: list[str]) -> int:
    from services import storage, pg_sync
    from db.client import get_db_connection

    period = argv[1] if len(argv) > 1 else None
    if not period:
        period = _newest_period_with_report(storage)
        if not period:
            print("FAIL: no reports found in Object Storage (reports/*/report.json).")
            return 2
        print(f"No period given — using newest with a report: {period}")

    try:
        result = verify(period, storage, pg_sync, get_db_connection)
    except Exception as exc:
        print(f"FAIL: verification errored for {period}: {type(exc).__name__}: {exc}")
        return 2

    print(f"\nPG mirror verification — period {result['period']}")
    print(f"  materialize_report() returned: {result['materialized']}")
    print(f"  {'section':<24} {'report':>7} {'in PG':>7}  result")
    print(f"  {'-'*24} {'-'*7} {'-'*7}  ------")
    for r in result["rows"]:
        print(f"  {r['label']:<24} {r['report_count']:>7} {r['pg_count']:>7}  {'OK' if r['ok'] else 'MISMATCH'}")

    if result["ok"]:
        print("\nPASS — every report section is mirrored into PostgreSQL.")
        return 0
    print("\nFAIL — a report section did not mirror into PostgreSQL (see MISMATCH above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
