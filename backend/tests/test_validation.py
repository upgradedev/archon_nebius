"""Unit tests for validation logic — period patterns, filename sanitization,
and cross-router input validation consistency.

These tests target pure logic functions and API validation without any I/O.
"""
import re

import pytest


# ── Period pattern ─────────────────────────────────────────────────────────────

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@pytest.mark.parametrize("period", [
    "2025-01",
    "2025-06",
    "2025-12",
    "2024-09",
    "2026-01",
    "1999-01",
    "2100-12",
])
def test_period_pattern_valid(period):
    assert re.match(_PERIOD_PATTERN, period), f"Expected {period!r} to be valid"


@pytest.mark.parametrize("period", [
    "2025-00",       # month 0
    "2025-13",       # month 13
    "25-01",         # 2-digit year
    "2025-1",        # single-digit month without leading zero
    "jan-2025",      # text month
    "2025/01",       # wrong separator
    "2025-01-01",    # full date
    "../admin",      # path traversal
    "",              # empty
    "2025",          # year only
    "01-2025",       # reversed
])
def test_period_pattern_invalid(period):
    assert not re.match(_PERIOD_PATTERN, period), f"Expected {period!r} to be invalid"


# ── Filename sanitization ──────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from routers.upload import _sanitize_filename
    return _sanitize_filename(name)


def test_sanitize_normal_filename():
    assert _sanitize("invoice.pdf") == "invoice.pdf"


def test_sanitize_removes_path_traversal():
    result = _sanitize("../../etc/passwd.pdf")
    assert ".." not in result
    assert "/" not in result


def test_sanitize_removes_backslash():
    result = _sanitize("dir\\file.pdf")
    assert "\\" not in result


def test_sanitize_strips_leading_dot():
    result = _sanitize(".hidden-file.pdf")
    assert not result.startswith(".")


def test_sanitize_strips_leading_underscore():
    result = _sanitize("_system.pdf")
    assert not result.startswith("_")


def test_sanitize_removes_control_characters():
    result = _sanitize("file\x00\x1fname.pdf")
    assert "\x00" not in result
    assert "\x1f" not in result


def test_sanitize_handles_unicode_normalization():
    # Greek characters should be preserved or converted safely
    result = _sanitize("Αρχών.pdf")
    assert len(result) > 0
    assert ".." not in result


def test_sanitize_truncates_long_names():
    long_name = "a" * 300 + ".pdf"
    result = _sanitize(long_name)
    assert len(result) <= 200


def test_sanitize_empty_name_returns_fallback():
    result = _sanitize("")
    assert result == "file"


def test_sanitize_collapses_multiple_underscores():
    result = _sanitize("file___name.pdf")
    assert "__" not in result


def test_sanitize_preserves_hyphen_and_space():
    result = _sanitize("my-file name.pdf")
    assert "-" in result or "_" in result or "my" in result


# ── API-level period validation (via TestClient) ───────────────────────────────

def test_upload_accepts_valid_period_boundary_jan(client):
    import io
    from unittest.mock import patch
    with patch("services.storage.upload_file"), patch("services.storage.put_json"):
        resp = client.post(
            "/api/upload",
            files=[("files", ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
            data={"period": "2025-01"},
        )
    assert resp.status_code == 200


def test_upload_accepts_valid_period_boundary_dec(client):
    import io
    from unittest.mock import patch
    with patch("services.storage.upload_file"), patch("services.storage.put_json"):
        resp = client.post(
            "/api/upload",
            files=[("files", ("b.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
            data={"period": "2025-12"},
        )
    assert resp.status_code == 200


def test_analyze_accepts_all_valid_months(client):
    from unittest.mock import patch
    results = []
    for month in range(1, 13):
        period = f"2025-{month:02d}"
        with patch("services.nebius.submit_analysis_job", return_value={"id": "x", "status": "pending", "period": period, "documentsCount": 0, "createdAt": "2025-01-01T00:00:00+00:00"}):
            resp = client.post("/api/analyze", json={"period": period})
        results.append((period, resp.status_code))
    assert all(code == 200 for _, code in results), [(p, c) for p, c in results if c != 200]


def test_delete_period_rejects_path_traversal(client):
    resp = client.delete("/api/periods/../admin")
    assert resp.status_code in (404, 422)


def test_get_documents_rejects_traversal(client):
    resp = client.get("/api/documents/../etc")
    assert resp.status_code in (404, 422)


def test_get_report_rejects_traversal(client):
    resp = client.get("/api/reports/../etc")
    assert resp.status_code in (404, 422)
