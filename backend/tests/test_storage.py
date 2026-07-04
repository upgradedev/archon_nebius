"""Unit tests for services/storage.py helper functions."""
from unittest.mock import MagicMock, patch, call
import json
import pytest


@pytest.fixture
def mock_s3(monkeypatch):
    """Patch boto3.client to return a reusable mock S3 client."""
    s3 = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **kw: s3)
    return s3


# ── upload_file ───────────────────────────────────────────────────────────────

def test_upload_file_calls_put_object(mock_s3):
    from services.storage import upload_file
    upload_file("some/key.pdf", b"content", "application/pdf")
    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="some/key.pdf",
        Body=b"content",
        ContentType="application/pdf",
    )


def test_upload_file_returns_key(mock_s3):
    from services.storage import upload_file
    result = upload_file("path/to/file.pdf", b"data")
    assert result == "path/to/file.pdf"


# ── download_json ─────────────────────────────────────────────────────────────

def test_download_json_parses_body(mock_s3):
    payload = {"hello": "world"}
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(payload).encode())
    }
    from services.storage import download_json
    result = download_json("reports/2025-01/report.json")
    assert result == payload


# ── list_keys ─────────────────────────────────────────────────────────────────

def test_list_keys_returns_all_pages(mock_s3):
    paginator = MagicMock()
    pages = [
        {"Contents": [{"Key": "a/1.pdf"}, {"Key": "a/2.pdf"}]},
        {"Contents": [{"Key": "a/3.pdf"}]},
    ]
    paginator.paginate.return_value = iter(pages)
    mock_s3.get_paginator.return_value = paginator

    from services.storage import list_keys
    keys = list_keys("a/")
    assert sorted(keys) == ["a/1.pdf", "a/2.pdf", "a/3.pdf"]


def test_list_keys_empty_prefix(mock_s3):
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{"Contents": []}])
    mock_s3.get_paginator.return_value = paginator

    from services.storage import list_keys
    assert list_keys("missing/") == []


# ── put_json ──────────────────────────────────────────────────────────────────

def test_put_json_serialises_and_uploads(mock_s3):
    from services.storage import put_json
    put_json("company/profile.json", {"company_name": "Test"})
    mock_s3.put_object.assert_called_once()
    _, kwargs = mock_s3.put_object.call_args
    body = kwargs.get("Body") or mock_s3.put_object.call_args.kwargs.get("Body")
    parsed = json.loads(body)
    assert parsed["company_name"] == "Test"


# ── delete_prefix ─────────────────────────────────────────────────────────────

def test_delete_prefix_batches_1000(mock_s3):
    # 1500 objects — should result in two delete_objects calls
    paginator = MagicMock()
    paginator.paginate.return_value = iter([
        {"Contents": [{"Key": f"prefix/{i}.pdf"} for i in range(1500)]}
    ])
    mock_s3.get_paginator.return_value = paginator

    from services.storage import delete_prefix
    count = delete_prefix("prefix/")
    assert count == 1500
    assert mock_s3.delete_objects.call_count == 2


def test_delete_prefix_empty_prefix_does_nothing(mock_s3):
    from services.storage import delete_prefix
    count = delete_prefix("")
    assert count == 0
    mock_s3.delete_objects.assert_not_called()


def test_delete_prefix_no_objects(mock_s3):
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{"Contents": []}])
    mock_s3.get_paginator.return_value = paginator

    from services.storage import delete_prefix
    count = delete_prefix("nonexistent/")
    assert count == 0
    mock_s3.delete_objects.assert_not_called()


# ── key_exists ────────────────────────────────────────────────────────────────

def test_key_exists_true(mock_s3):
    mock_s3.head_object.return_value = {}
    from services.storage import key_exists
    assert key_exists("some/key.pdf") is True


def test_key_exists_false(mock_s3):
    from botocore.exceptions import ClientError
    mock_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    from services.storage import key_exists
    assert key_exists("missing/key.pdf") is False
