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


def test_openapi_schema_reachable(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "paths" in resp.json()
