"""Signed-in end-to-end smoke test against the LIVE stack.

Exercises the authenticated path that the browser + BFF use in production:
Firebase Email/Password sign-in -> Bearer ID token -> /api/upload ->
/api/jobs -> /api/jobs/<id>. This is the path that was never automated
(it was a standing "user-only" TODO), which let two pysdk-shape bugs ship
to prod on the Nebius job path (create -> Operation.resource_id, status ->
check_presence). Keeping it here means CI catches a 401/500 regression.

Opt-in — skips cleanly unless creds are provided, so it never breaks the
default suite. TWO ways to supply an identity (headless-friendly first):

  A) Pre-minted session token (no Google sign-in call — best for CI/headless):
       NEBIUS_E2E_SESSION    a valid Firebase ID token (Bearer) for archon-pnl

  B) Email + password (this test mints the token via Firebase Identity Toolkit):
       E2E_FIREBASE_API_KEY  Firebase web API key for project archon-pnl
       E2E_EMAIL   (or NEBIUS_E2E_USER)      sign-in email (the e2e-test account)
       E2E_PASSWORD (or NEBIUS_E2E_PASSWORD) sign-in password

  BACKEND_URL             backend base url (default from conftest; use the
                          live https://archon-api.duckdns.org for a live run)

One-command runbook (headless, once you hold a token or the test account):

  # Path A — you already have an ID token:
  NEBIUS_E2E_SESSION=<id_token> BACKEND_URL=https://archon-api.duckdns.org \
    python -m pytest e2e/test_05_signed_in.py -v

  # Path B — email/password (the test mints the token):
  E2E_FIREBASE_API_KEY=<web_api_key> NEBIUS_E2E_USER=<email> \
    NEBIUS_E2E_PASSWORD=<password> BACKEND_URL=https://archon-api.duckdns.org \
    python -m pytest e2e/test_05_signed_in.py -v

The ONLY user-gated step is obtaining the token / creating the test account
(an interactive Google login). Everything after that is one command. The
unauthenticated-401 boundary check needs NO credentials and always runs.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

REPO_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_DIR / "sample-data"

# Path A: a pre-minted Firebase ID token — skips the sign-in network call.
_SESSION = os.environ.get("NEBIUS_E2E_SESSION")
# Path B: email/password sign-in. NEBIUS_E2E_USER/PASSWORD are accepted aliases
# for E2E_EMAIL/E2E_PASSWORD (the originals the signed-in-live CI job wires).
_API_KEY = os.environ.get("E2E_FIREBASE_API_KEY")
_EMAIL = os.environ.get("E2E_EMAIL") or os.environ.get("NEBIUS_E2E_USER")
_PASSWORD = os.environ.get("E2E_PASSWORD") or os.environ.get("NEBIUS_E2E_PASSWORD")

_HAS_SIGNIN = bool(_API_KEY and _EMAIL and _PASSWORD)
_HAS_IDENTITY = bool(_SESSION) or _HAS_SIGNIN

# NOTE: there is deliberately NO module-level `pytestmark` skip. Only the tests
# that actually need an identity carry `requires_creds`. The unauthenticated-401
# assertion needs no credentials, so it must NOT be gated behind them — otherwise
# the one check that guards the auth boundary silently skips alongside the
# credentialed tests (the original bug this split fixes). It runs whenever this
# module is collected against a real, auth-enabled backend.
requires_creds = pytest.mark.skipif(
    not _HAS_IDENTITY,
    reason=("signed-in e2e needs NEBIUS_E2E_SESSION (a Firebase ID token) OR "
            "E2E_FIREBASE_API_KEY + E2E_EMAIL/NEBIUS_E2E_USER + "
            "E2E_PASSWORD/NEBIUS_E2E_PASSWORD"),
)


@pytest.fixture(scope="module")
def id_token() -> str:
    # Path A — a pre-minted token is used verbatim; no outbound sign-in call.
    if _SESSION:
        return _SESSION
    # Path B — mint a fresh ID token from email/password via Identity Toolkit.
    r = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
        params={"key": _API_KEY},
        json={"email": _EMAIL, "password": _PASSWORD, "returnSecureToken": True},
        timeout=20,
    )
    r.raise_for_status()
    token = r.json().get("idToken")
    assert token, "Identity Toolkit returned no idToken"
    return token


@pytest.fixture(scope="module")
def auth_session(id_token) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {id_token}", "Accept": "application/json"})
    # The live endpoint serves a Caddy tls-internal cert (the BFF uses verify=False).
    s.verify = os.environ.get("E2E_VERIFY_TLS", "false").lower() == "true"
    return s


def _sample_pdfs() -> list[Path]:
    pdfs = sorted(SAMPLE_DIR.rglob("*.pdf"))
    if not pdfs:
        pytest.skip(f"No sample PDFs under {SAMPLE_DIR}")
    return pdfs[:3]


@requires_creds
def test_health_is_ok(base_url, auth_session):
    r = auth_session.get(f"{base_url}/health", timeout=20)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@requires_creds
def test_signed_in_upload_and_job_submit(base_url, auth_session, period):
    # Upload must be accepted (200) with the Bearer token and persist to storage.
    pdfs = _sample_pdfs()
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in pdfs]
    up = auth_session.post(f"{base_url}/api/upload", files=files, timeout=120)
    assert up.status_code == 200, up.text
    upload_id = up.json().get("uploadId")
    assert upload_id

    # Job submit must not 500 — regression guard for create -> Operation.resource_id.
    job = auth_session.post(
        f"{base_url}/api/jobs",
        json={"uploadId": upload_id, "period": period},
        timeout=60,
    )
    assert job.status_code == 200, job.text
    job_id = job.json().get("id")
    assert job_id and job_id.startswith("aijob-")

    # Status poll must not 500 — regression guard for the JobStatus wrapper shape.
    st = auth_session.get(f"{base_url}/api/jobs/{job_id}", timeout=30)
    assert st.status_code == 200, st.text
    assert st.json().get("status") in {"pending", "running", "completed", "failed"}


def test_unauthenticated_upload_is_rejected(base_url):
    # Belt-and-suspenders: no token -> 401 (not a 502/500).
    r = requests.post(
        f"{base_url}/api/upload",
        files=[("files", ("x.pdf", b"%PDF-1.4", "application/pdf"))],
        timeout=30,
        verify=os.environ.get("E2E_VERIFY_TLS", "false").lower() == "true",
    )
    assert r.status_code == 401, r.text
