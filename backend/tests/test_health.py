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


def _pg_conn_ok():
    from unittest.mock import MagicMock
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (1,)
    return conn


def test_health_db_reachable(client):
    """/health/db reports reachable=true when a connection + SELECT 1 succeed."""
    from unittest.mock import patch
    with patch("db.client.get_db_connection", return_value=_pg_conn_ok()):
        resp = client.get("/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["db"] == "ok"


def test_health_db_unreachable_is_not_500(client):
    """A PG timeout must surface as reachable=false (a pure signal), never a 500 —
    the whole point is to make the dead-mirror condition observable, not to crash."""
    from unittest.mock import patch
    with patch("db.client.get_db_connection", side_effect=OSError("timeout expired")):
        resp = client.get("/api/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
    assert body["db"] == "unreachable"
    assert "timeout" in body["detail"]


def test_health_db_no_auth_required(client):
    """PG reachability probe must be reachable without auth (deploy gate uses it)."""
    from unittest.mock import patch
    with patch("db.client.get_db_connection", return_value=_pg_conn_ok()):
        resp = client.get("/health/db", headers={})
    assert resp.status_code == 200
