"""
Auth middleware tests.
The app fixture sets SKIP_AUTH=true, so the default client bypasses Firebase.
Tests that need real auth behaviour override the env var temporarily.
"""
import os
import pytest
from fastapi.testclient import TestClient


def test_skip_auth_allows_protected_endpoint(client):
    """With SKIP_AUTH=true the /api/periods endpoint must respond (not 401)."""
    from unittest.mock import patch
    with patch("services.storage.list_keys", return_value=[]):
        resp = client.get("/api/periods")
    assert resp.status_code == 200


def test_missing_token_returns_401_when_auth_enabled():
    """Without SKIP_AUTH a missing Bearer token must return 401."""
    # Temporarily disable skip-auth for this test only
    orig = os.environ.pop("SKIP_AUTH", None)
    try:
        # Re-import auth module with skip flag off
        import importlib
        import auth as auth_module
        auth_module._SKIP_AUTH = False

        from fastapi.testclient import TestClient
        from main import app
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.get("/api/periods")
        assert resp.status_code == 401
    finally:
        if orig is not None:
            os.environ["SKIP_AUTH"] = orig
        import auth as auth_module  # type: ignore[import]
        auth_module._SKIP_AUTH = True


def test_skip_auth_injects_ci_user(client):
    """With SKIP_AUTH the token payload for CI user is returned internally."""
    import auth
    payload = auth.verify_firebase_token(None)
    assert payload["uid"] == "ci-test-user"
    assert "email" in payload


def _client_with_auth_enabled():
    """Build a TestClient with Firebase verification ACTIVE (SKIP_AUTH off).

    Mirrors test_missing_token_returns_401_when_auth_enabled but returns the
    client so a test can attach an Authorization header.
    """
    import auth as auth_module
    from fastapi.testclient import TestClient
    from main import app
    auth_module._SKIP_AUTH = False
    return TestClient(app, raise_server_exceptions=False)


def test_bogus_bearer_token_returns_401_when_auth_enabled():
    """A malformed Bearer token must be rejected with 401 by the middleware.

    NOTE: this codebase verifies Firebase ID tokens with PyJWT + Google's JWKS
    (see backend/auth.py), not the firebase_admin Admin SDK. The audit item's
    'mock firebase_admin.auth.verify_id_token to raise' maps here to driving a
    token that cannot pass verification. A structurally-malformed token fails at
    jwt.get_unverified_header BEFORE any key fetch, so this stays fully OFFLINE
    (no call to googleapis.com) — important inside the no-network coverage gate.
    """
    orig = os.environ.pop("SKIP_AUTH", None)
    try:
        tc = _client_with_auth_enabled()
        resp = tc.get("/api/periods", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert resp.status_code == 401, resp.text
    finally:
        if orig is not None:
            os.environ["SKIP_AUTH"] = orig
        import auth as auth_module
        auth_module._SKIP_AUTH = True


def test_verification_failure_returns_401_without_network(monkeypatch):
    """When token verification raises, the middleware returns 401 — and never
    leaks the failure as a 500. We patch the verification internals so a
    well-formed-looking token is rejected without any outbound network call
    (analogous to firebase_admin.auth.verify_id_token raising).
    """
    orig = os.environ.pop("SKIP_AUTH", None)
    try:
        import auth as auth_module
        # Force the verify path to raise as if the token were invalid, with no
        # network: stub header parse + key fetch + decode.
        monkeypatch.setattr(auth_module.jwt, "get_unverified_header",
                            lambda token: {"kid": "test-kid"})
        monkeypatch.setattr(auth_module, "_public_keys", lambda: {"test-kid": "cert-pem"})
        monkeypatch.setattr(auth_module.x509, "load_pem_x509_certificate",
                            lambda data: (_ for _ in ()).throw(ValueError("bad cert")))

        tc = _client_with_auth_enabled()
        resp = tc.get("/api/periods", headers={"Authorization": "Bearer header.payload.sig"})
        assert resp.status_code == 401, resp.text
        assert "Invalid token" in resp.text
    finally:
        if orig is not None:
            os.environ["SKIP_AUTH"] = orig
        import auth as auth_module
        auth_module._SKIP_AUTH = True
