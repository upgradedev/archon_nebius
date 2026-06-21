"""Stage 0 — the live stack is up and the API contract is reachable."""


def test_backend_health(http, base_url):
    r = http.get(f"{base_url}/health", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "archon-backend"


def test_openapi_schema_served(http, base_url):
    r = http.get(f"{base_url}/openapi.json", timeout=30)
    assert r.status_code == 200
    schema = r.json()
    paths = schema.get("paths", {})
    # Every pipeline endpoint must be present in the contract.
    for p in ["/api/upload", "/api/jobs", "/api/analyze", "/api/reports/{period}",
              "/api/documents/{period}", "/api/periods"]:
        assert p in paths, f"missing endpoint in OpenAPI: {p}"


def test_periods_endpoint_reachable(http, base_url):
    r = http.get(f"{base_url}/api/periods", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
