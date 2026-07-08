#!/usr/bin/env python3
"""
Purge ALL real uploaded data from the Archon production store.

Why this exists
---------------
The app's Firebase auth (`verify_firebase_token`) only *gates* access — it does
NOT scope data per user. Object Storage keys are global by period
(``raw-docs/{period}/{upload_id}/...``) and the Postgres tables hold every
upload, so ANY signed-in user (e.g. a challenge judge) sees ALL uploaded
documents — including the owner's real "Reflective" test PII.

This script wipes the production store back to a clean slate:

  * Object Storage: list-then-delete every object under the three data prefixes
    ``raw-docs/``, ``extracted/``, ``reports/`` — and NOTHING else (the bucket
    may also hold Caddy TLS cert material; we never touch it).
  * Postgres: TRUNCATE the six data tables with RESTART IDENTITY CASCADE.

It is idempotent: re-running on an already-empty store is a no-op and still
prints a clean 0/0 summary.

Credentials come from env only (this runs in CI, which holds the prod secrets):
  * NEBIUS_STORAGE_ACCESS_KEY_ID / NEBIUS_STORAGE_SECRET_KEY  — S3 creds
  * STORAGE_ENDPOINT_URL (default https://storage.eu-west1.nebius.cloud)
  * NEBIUS_BUCKET_NAME  (default archon-bucket)
  * NEBIUS_REGION       (default eu-west1)
  * DATABASE_URL        — full Postgres connection string
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# ── Storage config ──────────────────────────────────────────────────────────
STORAGE_ENDPOINT_URL = os.getenv(
    "STORAGE_ENDPOINT_URL", "https://storage.eu-west1.nebius.cloud"
)
BUCKET = os.getenv("NEBIUS_BUCKET_NAME", "archon-bucket")
REGION = os.getenv("NEBIUS_REGION", "eu-west1")

# ONLY these prefixes. The bucket may also hold Caddy TLS cert material and
# other operational objects — a full-bucket wipe would break backend HTTPS.
DATA_PREFIXES = ["raw-docs/", "extracted/", "reports/"]

# ── Postgres config ─────────────────────────────────────────────────────────
# Order matters only cosmetically — CASCADE handles FK deps — but list children
# first for readability.
DATA_TABLES = [
    "documents",
    "employees",
    "employee_payroll",
    "payroll_events",
    "payroll_event_payslips",
    "validation_results",
]


# ─────────────────────────────────────────────────────────────────────────────
# Object Storage
# ─────────────────────────────────────────────────────────────────────────────
def _s3_client():
    access_key = os.getenv("NEBIUS_STORAGE_ACCESS_KEY_ID")
    secret_key = os.getenv("NEBIUS_STORAGE_SECRET_KEY")
    if not access_key or not secret_key:
        raise SystemExit(
            "ERROR: NEBIUS_STORAGE_ACCESS_KEY_ID / NEBIUS_STORAGE_SECRET_KEY "
            "are not set — cannot connect to Object Storage."
        )
    # Mirror backend/services/storage.py: SigV4 + explicit region, or Nebius
    # rejects the signature (the eu-north1-vs-eu-west1 mismatch that once
    # surfaced as a /upload 500).
    return boto3.client(
        "s3",
        endpoint_url=STORAGE_ENDPOINT_URL,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=REGION,
        config=Config(signature_version="s3v4"),
    )


def _list_keys(s3, prefix: str) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _delete_keys(s3, keys: list[str]) -> int:
    if not keys:
        return 0
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = [{"Key": k} for k in keys[i : i + 1000]]
        resp = s3.delete_objects(Bucket=BUCKET, Delete={"Objects": batch})
        deleted += len(resp.get("Deleted", batch))
        errors = resp.get("Errors", [])
        if errors:
            for e in errors[:10]:
                print(
                    f"    ! delete error: {e.get('Key')} — "
                    f"{e.get('Code')}: {e.get('Message')}"
                )
            raise RuntimeError(f"{len(errors)} object(s) failed to delete")
    return deleted


def purge_storage() -> bool:
    print("=" * 70)
    print("OBJECT STORAGE")
    print(f"  endpoint : {STORAGE_ENDPOINT_URL}")
    print(f"  bucket   : {BUCKET}")
    print(f"  region   : {REGION}")
    print(f"  prefixes : {', '.join(DATA_PREFIXES)}")
    print("=" * 70)

    s3 = _s3_client()

    total_found = 0
    total_deleted = 0
    for prefix in DATA_PREFIXES:
        keys = _list_keys(s3, prefix)
        found = len(keys)
        deleted = _delete_keys(s3, keys)
        total_found += found
        total_deleted += deleted
        print(f"  {prefix:<12} found={found:<6} deleted={deleted}")

    # VERIFY: re-list every prefix and assert nothing remains.
    print("  --- verify (re-list) ---")
    ok = True
    for prefix in DATA_PREFIXES:
        remaining = len(_list_keys(s3, prefix))
        status = "OK" if remaining == 0 else "STILL PRESENT"
        print(f"  {prefix:<12} remaining={remaining:<6} [{status}]")
        if remaining != 0:
            ok = False

    print(f"  SUMMARY: found={total_found} deleted={total_deleted} "
          f"-> {'EMPTY' if ok else 'NOT EMPTY'}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Postgres
# ─────────────────────────────────────────────────────────────────────────────
def _safe_dsn_label(dsn: str) -> str:
    """host:port/dbname only — never log the password (ADR-005 / gitleaks)."""
    try:
        p = urlparse(dsn)
        host = p.hostname or "?"
        port = p.port or "?"
        db = (p.path or "/").lstrip("/") or "?"
        return f"{host}:{port}/{db}"
    except Exception:
        return "<unparseable DATABASE_URL>"


def _with_port(dsn: str, port: int) -> str:
    p = urlparse(dsn)
    host = p.hostname or ""
    userinfo = ""
    if p.username:
        userinfo = p.username
        if p.password:
            userinfo += f":{p.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}:{port}"
    return urlunparse(p._replace(netloc=netloc))


def _connect(dsn: str):
    import psycopg2

    parsed = urlparse(dsn)
    # Known Nebius gotcha (CLAUDE.md): pgBouncer 6432 is firewalled; the direct
    # port is 5432. If the URL points at 6432 and the connect fails, retry 5432.
    candidates = [dsn]
    if parsed.port == 6432:
        candidates.append(_with_port(dsn, 5432))

    last_err: Exception | None = None
    for candidate in candidates:
        label = _safe_dsn_label(candidate)
        try:
            print(f"  connecting to {label} ...")
            conn = psycopg2.connect(candidate, connect_timeout=10)
            print(f"  connected to {label}")
            return conn
        except Exception as e:  # noqa: BLE001 - surface exact driver error
            last_err = e
            print(f"  connect FAILED for {label}: {type(e).__name__}: {e}")
    assert last_err is not None
    raise last_err


def _counts(cur) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in DATA_TABLES:
        cur.execute(f"SELECT count(*) FROM {table};")
        result[table] = cur.fetchone()[0]
    return result


def purge_database() -> bool:
    print()
    print("=" * 70)
    print("POSTGRES")
    print("=" * 70)

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("ERROR: DATABASE_URL is not set — cannot connect to Postgres.")

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            before = _counts(cur)
            print("  --- row counts BEFORE ---")
            for t in DATA_TABLES:
                print(f"    {t:<24} {before[t]}")

            # RESTART IDENTITY resets sequences; CASCADE handles FK dependents.
            table_list = ", ".join(DATA_TABLES)
            cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;")
            conn.commit()

            after = _counts(cur)
            print("  --- row counts AFTER ---")
            ok = True
            for t in DATA_TABLES:
                status = "OK" if after[t] == 0 else "NOT EMPTY"
                print(f"    {t:<24} {after[t]} [{status}]")
                if after[t] != 0:
                    ok = False
        return ok
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("Archon production store purge")
    print()

    storage_err = None
    db_err = None
    storage_ok = False
    db_ok = False

    try:
        storage_ok = purge_storage()
    except Exception as e:  # noqa: BLE001
        storage_err = e
        print(f"  STORAGE PURGE FAILED: {type(e).__name__}: {e}")

    try:
        db_ok = purge_database()
    except Exception as e:  # noqa: BLE001
        db_err = e
        print(f"  DATABASE PURGE FAILED: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print(f"  Object Storage : {'EMPTY (0 objects)' if storage_ok else 'FAILED / NOT EMPTY'}")
    print(f"  Postgres       : {'EMPTY (0 rows)' if db_ok else 'FAILED / NOT EMPTY'}")
    print("=" * 70)

    if storage_err or db_err or not storage_ok or not db_ok:
        return 1
    print("PURGE COMPLETE — production store is empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
