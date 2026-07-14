"""Best-effort audit trail of AI-Job submissions (the `job_runs` table).

Why this exists
    A submitted job leaves only an ephemeral Object Storage idempotency marker;
    there was no durable, queryable record of what ran, when, and WHO ran it. This
    records every submission in PostgreSQL so the serverless pipeline has an audit
    trail, and so a query for recent runs by a non-test identity can detect a third
    party (e.g. a judge) running a live test.

Design contract (same as services/pg_sync.py):
    * BEST-EFFORT. record_job_run() NEVER raises. On any failure it logs a warning,
      rolls back, and returns False. A DB hiccup must never break a job submission —
      Object Storage markers stay the runtime source of truth.
    * The write is keyed by the Nebius job id; a re-recorded id is deduped so a
      retried submit does not create duplicate rows.
"""
import logging

logger = logging.getLogger(__name__)


def record_job_run(job: dict, job_type: str, identity: dict | None = None) -> bool:
    """Record a submitted job in `job_runs`. Returns True on a committed write,
    False on any failure / nothing to write. Never raises.

    `job` is the dict returned by the submit helpers (id, status, period,
    nebius_job_name). `identity` is the verified Firebase claims ({uid, email}).
    """
    job_id = (job or {}).get("id")
    if not job_id:
        return False

    uid = (identity or {}).get("uid")
    email = (identity or {}).get("email")

    try:
        from db.client import get_db_connection
        conn = get_db_connection()
    except Exception as exc:
        logger.warning("job_runs audit skipped for %s — no DB connection: %s", job_id, exc)
        return False

    try:
        with conn.cursor() as cur:
            # Dedupe on job_id so a retried submit does not add a duplicate row.
            cur.execute(
                """
                INSERT INTO job_runs
                    (job_id, nebius_job_name, job_type, period, status,
                     submitted_by, submitted_email)
                SELECT %s, %s, %s, %s, %s, %s, %s
                WHERE NOT EXISTS (SELECT 1 FROM job_runs WHERE job_id = %s)
                """,
                (
                    job_id,
                    job.get("nebius_job_name"),
                    job_type,
                    job.get("period"),
                    job.get("status"),
                    uid,
                    email,
                    job_id,
                ),
            )
        conn.commit()
        logger.info("job_runs audit recorded %s (%s) by %s", job_id, job_type, email or uid or "anon")
        return True
    except Exception as exc:
        logger.warning("job_runs audit failed for %s — rolling back: %s", job_id, exc)
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


def list_recent_job_runs(limit: int = 100, since_hours: int | None = None,
                         exclude_identities: list[str] | None = None) -> list[dict]:
    """Return recent job_runs, newest first. Never raises (returns [] on failure).

    `exclude_identities` filters out known identities (our own test/judge accounts)
    from both submitted_by and submitted_email, so what remains is third-party
    activity — the signal that someone external ran a live test.
    """
    try:
        from db.client import get_db_connection
        conn = get_db_connection()
    except Exception as exc:
        logger.warning("job_runs list skipped — no DB connection: %s", exc)
        return []

    try:
        clauses = []
        params: list = []
        if since_hours is not None:
            clauses.append("created_at >= now() - (%s || ' hours')::interval")
            params.append(int(since_hours))
        excl = [e for e in (exclude_identities or []) if e]
        if excl:
            clauses.append("COALESCE(submitted_by,'') <> ALL(%s) AND COALESCE(submitted_email,'') <> ALL(%s)")
            params.extend([excl, excl])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(int(limit))
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT job_id, nebius_job_name, job_type, period, status,
                       submitted_by, submitted_email, created_at
                FROM job_runs
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        # created_at -> isoformat for JSON.
        for r in rows:
            ca = r.get("created_at")
            if ca is not None and hasattr(ca, "isoformat"):
                r["created_at"] = ca.isoformat()
        return rows
    except Exception as exc:
        logger.warning("job_runs list failed: %s", exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
