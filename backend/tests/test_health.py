def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "archon-backend"


def test_health_no_auth_required(client):
    """Health must be reachable without an Authorization header."""
    resp = client.get("/health", headers={})
    assert resp.status_code == 200


def test_api_health_returns_ok(client):
    """The BFF only rewrites /api/** to the backend, so the frontend cold-start
    poller probes /api/health — it must exist and return 200 when warm."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_health_no_auth_required(client):
    """The liveness probe must be reachable without an Authorization header."""
    resp = client.get("/api/health", headers={})
    assert resp.status_code == 200


def test_openapi_schema_reachable(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "paths" in resp.json()
