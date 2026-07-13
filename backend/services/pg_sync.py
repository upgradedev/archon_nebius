"""Backend-side materialization of a completed financial report into the
PostgreSQL read-model tables.

Why this lives in the backend (not the analysis Job):
    The analysis Job writes the authoritative report to Object Storage
    (reports/{period}/report.json). The relational tables
    (employees / employee_payroll / payroll_events / validation_results) mirror
    that report so the API can serve relational queries. The Managed PostgreSQL
    cluster is IP-allowlisted and reachable from the backend Endpoint (same VPC),
    NOT from an ephemeral Job container — so the backend is the correct writer.
    This closes the "roadmap item" noted at the top of backend/db/schema.sql.

Design contract:
    * BEST-EFFORT. materialize_report() NEVER raises. On any failure it logs a
      warning, rolls back, and returns False. The report response path is the
      source of truth and must never break because a mirror write failed — the
      same graceful-degradation contract as the read side (S3 fallback).
    * IDEMPOTENT. Re-running for the same period replaces that period's rows, so
      materializing on every report read converges instead of duplicating.
    * The `documents` table is intentionally NOT touched here — it has its own
      writer (user document review, PUT /documents/{period}); mirroring the
      report must not clobber user-reviewed rows. Document-level foreign keys on
      the payroll tables are therefore left NULL (all such columns are nullable).
"""
import logging

logger = logging.getLogger(__name__)


def _num(value):
    """Coerce to float or None (schema numeric columns are all nullable)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_report(payload: dict) -> dict:
    """The stored object is {jobId, report, generatedAt}; accept either the
    wrapper or a bare FinancialReport dict."""
    if isinstance(payload, dict) and isinstance(payload.get("report"), dict):
        return payload["report"]
    return payload if isinstance(payload, dict) else {}


def materialize_report(period: str, payload: dict) -> bool:
    """Mirror a completed report's relational data into PostgreSQL for `period`.

    Returns True on a committed write, False on any failure or when there is
    nothing to write / no database configured. Never raises.
    """
    report = _extract_report(payload)
    if not report:
        return False

    payroll_events = report.get("payrollEvents") or []
    employees = report.get("employeeSummaries") or []
    validations = report.get("validationResults") or []

    if not (payroll_events or employees or validations):
        # Nothing relational to mirror (e.g. a pure-invoice period) — not a failure.
        return False

    try:
        from db.client import get_db_connection
        conn = get_db_connection()
    except Exception as exc:
        logger.warning("PG materialization skipped for %s — no DB connection: %s", period, exc)
        return False

    try:
        with conn.cursor() as cur:
            # Idempotent replace of this period's mirrored rows. employees is a
            # global master keyed by employee_code, so it is upserted (not
            # period-deleted) to preserve cross-period employee identity.
            cur.execute("DELETE FROM validation_results WHERE period = %s", (period,))
            cur.execute("DELETE FROM employee_payroll WHERE period = %s", (period,))
            cur.execute("DELETE FROM payroll_events WHERE period = %s", (period,))

            for v in validations:
                cur.execute(
                    """
                    INSERT INTO validation_results
                        (period, rule, passed, severity, message, source_files)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        period,
                        v.get("rule") or "unknown",
                        bool(v.get("passed")),
                        v.get("severity") or "info",
                        v.get("message"),
                        v.get("source_files") or [],
                    ),
                )

            for e in payroll_events:
                cur.execute(
                    """
                    INSERT INTO payroll_events
                        (period, company_name, net_total, gross_total,
                         employer_cost_total, employee_count, is_complete)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (period, company_name) DO UPDATE SET
                        net_total           = EXCLUDED.net_total,
                        gross_total         = EXCLUDED.gross_total,
                        employer_cost_total = EXCLUDED.employer_cost_total,
                        employee_count      = EXCLUDED.employee_count,
                        is_complete         = EXCLUDED.is_complete
                    """,
                    (
                        period,
                        e.get("company_name"),
                        _num(e.get("net_total")),
                        _num(e.get("gross_total")),
                        _num(e.get("employer_cost_total")),
                        _int(e.get("employee_count")),
                        bool(e.get("bank_confirmed")),
                    ),
                )

            for emp in employees:
                code = emp.get("employee_code")
                name = emp.get("employee_name")
                # employee_code is the UNIQUE master key. Postgres treats NULLs
                # as distinct, so a missing code would create duplicates — derive
                # a stable synthetic key from the name, or skip if neither exists.
                if not code:
                    if not name:
                        continue
                    code = f"{period}:{name}"

                cur.execute(
                    """
                    INSERT INTO employees (employee_code, full_name)
                    VALUES (%s, %s)
                    ON CONFLICT (employee_code) DO UPDATE SET
                        full_name  = COALESCE(EXCLUDED.full_name, employees.full_name),
                        updated_at = now()
                    RETURNING id
                    """,
                    (code, name),
                )
                employee_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO employee_payroll
                        (employee_id, period, gross_pay, net_pay, employer_cost)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (employee_id, period) DO UPDATE SET
                        gross_pay     = EXCLUDED.gross_pay,
                        net_pay       = EXCLUDED.net_pay,
                        employer_cost = EXCLUDED.employer_cost
                    """,
                    (
                        employee_id,
                        period,
                        _num(emp.get("gross_pay")),
                        # net_pay is NOT NULL in the schema — default to 0.0.
                        _num(emp.get("net_pay")) or 0.0,
                        _num(emp.get("employer_cost")),
                    ),
                )

        conn.commit()
        logger.info(
            "PG materialization committed for %s — %d payroll events, %d employees, %d validations",
            period, len(payroll_events), len(employees), len(validations),
        )
        return True
    except Exception as exc:
        logger.warning("PG materialization failed for %s — rolling back: %s", period, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
