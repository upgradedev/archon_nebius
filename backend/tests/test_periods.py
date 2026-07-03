"""Unit tests for GET /api/periods, DELETE /api/periods/{period},
GET /api/documents/{period}, GET/PUT /api/company-profile."""
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _client_error(code: str):
    error = {"Error": {"Code": code, "Message": "Mock error"}}
    return ClientError(error, "GetObject")


# ── GET /api/periods ──────────────────────────────────────────────────────────

def test_list_periods_empty(client):
    with patch("services.storage.list_keys", return_value=[]):
        resp = client.get("/api/periods")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_periods_with_data(client):
    def _list_keys(prefix):
        if prefix == "raw-docs/":
            return ["raw-docs/2025-01/abc/file.pdf", "raw-docs/2025-02/xyz/file.pdf"]
        if prefix == "extracted/":
            return ["extracted/2025-01/documents.json"]
        if prefix == "reports/":
            return ["reports/2025-01/report.json"]
        return []

    with patch("services.storage.list_keys", side_effect=_list_keys):
        resp = client.get("/api/periods")

    assert resp.status_code == 200
    data = resp.json()
    periods = {p["period"]: p for p in data}

    assert "2025-01" in periods
    assert periods["2025-01"]["hasReport"] is True
    assert periods["2025-01"]["hasExtraction"] is True

    assert "2025-02" in periods
    assert periods["2025-02"]["hasReport"] is False
    assert periods["2025-02"]["hasExtraction"] is False


def test_list_periods_sorted_descending(client):
    def _list_keys(prefix):
        if prefix == "raw-docs/":
            return ["raw-docs/2024-06/x/f.pdf", "raw-docs/2025-03/y/f.pdf", "raw-docs/2024-12/z/f.pdf"]
        return []

    with patch("services.storage.list_keys", side_effect=_list_keys):
        resp = client.get("/api/periods")

    periods = [p["period"] for p in resp.json()]
    assert periods == sorted(periods, reverse=True)


# ── DELETE /api/periods/{period} ──────────────────────────────────────────────

def test_delete_period(client):
    with patch("services.storage.delete_prefix", return_value=3) as mock_del:
        resp = client.delete("/api/periods/2025-01")

    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "2025-01"
    assert body["deleted"] == 9  # 3 prefixes × 3 each
    # Verify all three prefix paths were cleaned up
    calls = [c.args[0] for c in mock_del.call_args_list]
    assert any("raw-docs/2025-01/" in c for c in calls)
    assert any("extracted/2025-01/" in c for c in calls)
    assert any("reports/2025-01/" in c for c in calls)


# ── GET /api/documents/{period} ──────────────────────────────────────────────

def test_get_documents_found(client):
    docs = [{"filename": "invoice.pdf", "doc_type": "invoice", "total_amount": 1200.0}]
    with patch("services.storage.list_keys", return_value=["extracted/2025-01/up1/documents.json"]), \
         patch("services.storage.download_json",
               return_value={"period": "2025-01", "upload_id": "up1", "documents": docs}):
        resp = client.get("/api/documents/2025-01")
    assert resp.status_code == 200
    assert resp.json() == docs


def test_get_documents_aggregates_multiple_uploads(client):
    """Extraction writes one documents.json per upload batch; the endpoint merges them."""
    def _dl(key):
        if "up1" in key:
            return {"documents": [{"filename": "a.pdf", "doc_type": "invoice", "total_amount": 1.0}]}
        return {"documents": [{"filename": "b.pdf", "doc_type": "payslip", "total_amount": 2.0}]}

    with patch("services.storage.list_keys", return_value=[
                "extracted/2025-01/up1/documents.json",
                "extracted/2025-01/up2/documents.json"]), \
         patch("services.storage.download_json", side_effect=_dl):
        resp = client.get("/api/documents/2025-01")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {d["filename"] for d in body} == {"a.pdf", "b.pdf"}


def test_get_documents_not_found(client):
    with patch("services.storage.list_keys", return_value=[]):
        resp = client.get("/api/documents/2025-01")
    assert resp.status_code == 404


# ── PUT /api/documents/{period} ──────────────────────────────────────────────

def test_update_documents_writes_reviewed_and_deletes_originals(client):
    """Reviewed set is written dict-shaped at the reviewed key; the prior
    per-upload documents.json blobs are removed so analysis does not double-count."""
    docs = [
        {"source_file": "invoice.pdf", "doc_type": "invoice", "total_amount": 1200.0},
        {"source_file": "payslip.pdf", "doc_type": "payslip", "total_amount": 900.0},
    ]
    with patch("services.storage.list_keys", return_value=[
                "extracted/2025-01/up1/documents.json",
                "extracted/2025-01/up2/documents.json"]), \
         patch("services.storage.put_json", return_value="ok") as mock_put, \
         patch("services.storage.delete_key") as mock_del:
        resp = client.put("/api/documents/2025-01", json={"documents": docs})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"period": "2025-01", "documents": 2, "deleted": 2}

    # reviewed set written dict-shaped at the reviewed key
    key, payload = mock_put.call_args.args
    assert key == "extracted/2025-01/reviewed/documents.json"
    assert payload["period"] == "2025-01"
    assert payload["upload_id"] == "reviewed"
    assert payload["documents"] == docs

    # both prior per-upload blobs removed
    deleted_keys = {c.args[0] for c in mock_del.call_args_list}
    assert deleted_keys == {
        "extracted/2025-01/up1/documents.json",
        "extracted/2025-01/up2/documents.json",
    }


def test_update_documents_idempotent_excludes_reviewed_key(client):
    """A repeated review must not delete the reviewed blob it just wrote."""
    docs = [{"source_file": "a.pdf", "doc_type": "invoice"}]
    with patch("services.storage.list_keys", return_value=[
                "extracted/2025-01/reviewed/documents.json"]), \
         patch("services.storage.put_json", return_value="ok") as mock_put, \
         patch("services.storage.delete_key") as mock_del:
        resp = client.put("/api/documents/2025-01", json={"documents": docs})

    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0
    mock_put.assert_called_once()
    mock_del.assert_not_called()


def test_update_documents_rejects_bad_period(client):
    resp = client.put("/api/documents/not-a-period", json={"documents": []})
    assert resp.status_code == 422


# ── GET /api/company-profile ──────────────────────────────────────────────────

def test_get_company_profile_exists(client):
    profile = {"company_name": "Acme SA", "company_tax_id": "123456789"}
    with patch("services.storage.download_json", return_value=profile):
        resp = client.get("/api/company-profile")
    assert resp.status_code == 200
    assert resp.json()["company_name"] == "Acme SA"


def test_get_company_profile_missing_returns_empty(client):
    with patch("services.storage.download_json", side_effect=_client_error("NoSuchKey")):
        resp = client.get("/api/company-profile")
    assert resp.status_code == 200
    assert resp.json() == {"company_name": "", "company_tax_id": ""}


# ── PUT /api/company-profile ──────────────────────────────────────────────────

def test_update_company_profile(client):
    with patch("services.storage.put_json", return_value="company/profile.json") as mock_put:
        resp = client.put(
            "/api/company-profile",
            json={"company_name": "Beta Ltd", "company_tax_id": "987654321"},
        )
    assert resp.status_code == 200
    assert resp.json()["company_name"] == "Beta Ltd"
    mock_put.assert_called_once()
    key, data = mock_put.call_args.args
    assert key == "company/profile.json"
    assert data["company_name"] == "Beta Ltd"
