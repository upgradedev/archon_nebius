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
