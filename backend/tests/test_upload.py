"""Unit tests for POST /api/upload."""
import io
from unittest.mock import patch


def _pdf_bytes(name: str = "test") -> bytes:
    return b"%PDF-1.4 mock content for " + name.encode()


def _upload(client, filenames, period="2025-01", *, content_type="application/pdf"):
    files = [
        ("files", (fname, io.BytesIO(_pdf_bytes(fname)), content_type))
        for fname in filenames
    ]
    data = {"period": period}
    with patch("services.storage.upload_file", return_value="ok"), \
         patch("services.storage.put_json", return_value="ok"):
        return client.post("/api/upload", files=files, data=data)


# ── happy path ────────────────────────────────────────────────────────────────

def test_upload_single_file(client):
    resp = _upload(client, ["invoice.pdf"])
    assert resp.status_code == 200
    body = resp.json()
    assert "uploadId" in body
    assert len(body["files"]) == 1
    assert body["files"][0]["filename"] == "invoice.pdf"


def test_upload_multiple_files(client):
    names = ["invoice.pdf", "payroll.pdf", "receipt.jpg"]
    resp = _upload(client, names)
    assert resp.status_code == 200
    returned = [f["filename"] for f in resp.json()["files"]]
    assert sorted(returned) == sorted(names)


def test_upload_assigns_unique_upload_id(client):
    r1 = _upload(client, ["a.pdf"])
    r2 = _upload(client, ["b.pdf"])
    assert r1.json()["uploadId"] != r2.json()["uploadId"]


def test_upload_stores_raw_docs(client):
    with patch("services.storage.upload_file") as mock_upload, \
         patch("services.storage.put_json"):
        _upload(client, ["doc.pdf"], period="2025-03")
    called_keys = [c.args[0] for c in mock_upload.call_args_list]
    assert any("raw-docs/2025-03/" in k for k in called_keys)


def test_upload_writes_manifest(client):
    with patch("services.storage.upload_file"), \
         patch("services.storage.put_json") as mock_put:
        _upload(client, ["x.pdf"], period="2025-06")
    keys_written = [c.args[0] for c in mock_put.call_args_list]
    assert any("manifest.json" in k for k in keys_written)


# ── validation ────────────────────────────────────────────────────────────────

def test_upload_rejects_unsupported_extension(client):
    resp = _upload(client, ["script.exe"], content_type="application/octet-stream")
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_upload_rejects_empty_file_list(client):
    with patch("services.storage.upload_file"), patch("services.storage.put_json"):
        resp = client.post("/api/upload", data={"period": "2025-01"})
    assert resp.status_code in (400, 422)


def test_upload_rejects_too_many_files(client):
    names = [f"file{i}.pdf" for i in range(51)]
    resp = _upload(client, names)
    assert resp.status_code == 400
    assert "50" in resp.json()["detail"]
