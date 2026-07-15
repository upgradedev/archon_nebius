"""
BFF (Firebase Cloud Function) proxy tests — the regression guard for the
cold-start liveness probe (#115).

The BFF short-circuits any /api/** request that lacks an Authorization header
with a 401 "Missing bearer token". That 401 — NOT the backend's auth — was what
the unauthenticated /api/health poll hit, so the cold-start recovery could never
observe a 200. These tests assert:

  * unauthenticated GET /api/health is FORWARDED to the backend (httpx called)
    and returns the backend's real status — it is NOT short-circuited, and the
    BFF does NOT synthesize its own 200 (a cold 503 must pass through);
  * every other /api/** route still 401s without a bearer token.

`firebase_functions` is stubbed via sys.modules so the test needs only `httpx`
(already a backend dependency) and runs in CI without the Functions SDK.
"""

import json
import os
import sys
import types

# --- Stub the firebase_functions SDK before importing the function module. -----
_ff = types.ModuleType("firebase_functions")
_https = types.ModuleType("firebase_functions.https_fn")


class _Response:
    def __init__(self, response=None, status=None, headers=None):
        self.response = response
        self.status = status
        self.headers = headers or {}


def _on_request(*_args, **_kwargs):
    def _decorator(fn):
        return fn
    return _decorator


_https.Response = _Response
_https.Request = object
_https.on_request = _on_request
_ff.https_fn = _https
sys.modules["firebase_functions"] = _ff
sys.modules["firebase_functions.https_fn"] = _https

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402


class _FakeHeaders(dict):
    """Case-insensitive-ish header map matching what the proxy reads."""

    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeRequest:
    def __init__(self, method, path, headers=None, query_string=b"", body=b""):
        self.method = method
        self.path = path
        self.query_string = query_string
        self.full_path = path if not query_string else f"{path}?{query_string.decode()}"
        self.headers = _FakeHeaders(headers or {})
        self._body = body

    def get_data(self):
        return self._body


class _FakeBackendResponse:
    def __init__(self, status_code, content=b"{}", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def _install_backend(monkeypatch, status_code=200, content=b'{"status":"ok"}'):
    """Record calls to httpx.request and return a canned backend response."""
    calls = []

    def _fake_request(**kwargs):
        calls.append(kwargs)
        return _FakeBackendResponse(status_code, content)

    monkeypatch.setattr(main.httpx, "request", _fake_request)
    # The proxy requires NEBIUS_BACKEND_URL; tests configure a stand-in so they
    # exercise the forwarding path rather than the 503 misconfig guard.
    monkeypatch.setattr(main, "BACKEND_URL", "https://backend.example")
    return calls


def test_health_forwarded_without_auth(monkeypatch):
    """Unauthenticated GET /api/health must be FORWARDED, not short-circuited."""
    calls = _install_backend(monkeypatch, status_code=200)
    req = _FakeRequest("GET", "/api/health")
    resp = main.archon_proxy(req)
    assert len(calls) == 1, "health must reach the backend (httpx.request called)"
    assert calls[0]["url"].endswith("/api/health")
    # The backend is now reached over Nebius's managed HTTPS URL (trusted cert),
    # so the server-to-server hop verifies TLS. This is the whole point of the
    # native-HTTPS migration — never regress to verify=False.
    assert calls[0]["verify"] is True
    assert resp.status == 200


def test_missing_backend_url_returns_503(monkeypatch):
    """A function deployed without NEBIUS_BACKEND_URL fails loudly (503), never
    silently targets a dead hostname."""
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda **k: calls.append(k))
    monkeypatch.setattr(main, "BACKEND_URL", "")
    resp = main.archon_proxy(_FakeRequest("GET", "/api/health"))
    assert resp.status == 503
    assert calls == [], "must not attempt a request when the backend URL is unset"


def test_health_forwards_cold_status_not_synthesized(monkeypatch):
    """A cold backend (503) must pass through — the BFF must NOT fake a 200."""
    _install_backend(monkeypatch, status_code=503)
    req = _FakeRequest("GET", "/api/health")
    resp = main.archon_proxy(req)
    assert resp.status == 503


def test_health_trailing_slash_forwarded(monkeypatch):
    calls = _install_backend(monkeypatch, status_code=200)
    resp = main.archon_proxy(_FakeRequest("GET", "/api/health/"))
    assert len(calls) == 1
    assert resp.status == 200


def test_protected_route_still_401_without_auth(monkeypatch):
    """Every non-public /api/** route still requires a bearer token."""
    calls = _install_backend(monkeypatch, status_code=200)
    resp = main.archon_proxy(_FakeRequest("POST", "/api/upload"))
    assert resp.status == 401
    assert json.loads(resp.response)["detail"] == "Missing bearer token"
    assert calls == [], "protected route must not reach the backend without auth"


def test_health_forwarded_with_auth(monkeypatch):
    """Signed-in polling forwards too (auth header present)."""
    calls = _install_backend(monkeypatch, status_code=200)
    req = _FakeRequest("GET", "/api/health", headers={"Authorization": "Bearer x"})
    resp = main.archon_proxy(req)
    assert len(calls) == 1
    assert resp.status == 200


def test_non_get_health_requires_auth(monkeypatch):
    """The exemption is GET-only; a POST to /api/health is not public."""
    _install_backend(monkeypatch, status_code=200)
    resp = main.archon_proxy(_FakeRequest("POST", "/api/health"))
    assert resp.status == 401


def test_is_public_matrix():
    assert main._is_public("GET", "/api/health") is True
    assert main._is_public("GET", "/api/health/") is True
    assert main._is_public("get", "/api/health") is True
    assert main._is_public("GET", "/api/upload") is False
    assert main._is_public("POST", "/api/health") is False
    assert main._is_public("GET", "/api/healthz") is False
