"""Unit tests specifically targeting the database pathways in GET /api/periods,
DELETE /api/periods/{period}, GET /api/documents/{period}, and PUT /api/documents/{period}."""
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app


def test_list_periods_db_success():
    client = TestClient(app)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # SELECT DISTINCT period FROM documents returns 2026-03 and 2026-04
    mock_cursor.fetchall.return_value = [("2026-03",), ("2026-04",)]
    
    with patch("db.client.get_db_connection", return_value=mock_conn), \
         patch("services.storage.list_keys", return_value=["reports/2026-03/report.json"]):
        resp = client.get("/api/periods")
        
    assert resp.status_code == 200
    data = resp.json()
    # 2026-03 should have hasReport = True, 2026-04 hasReport = False
    periods = {p["period"]: p for p in data}
    assert "2026-03" in periods
    assert "2026-04" in periods
    assert periods["2026-03"]["hasReport"] is True
    assert periods["2026-03"]["hasExtraction"] is True
    assert periods["2026-04"]["hasReport"] is False
    assert periods["2026-04"]["hasExtraction"] is True


def test_delete_period_db_success():
    client = TestClient(app)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    with patch("db.client.get_db_connection", return_value=mock_conn), \
         patch("services.storage.delete_prefix", return_value=1):
        resp = client.delete("/api/periods/2026-03")
        
    assert resp.status_code == 200
    # SQL DELETEs should have been called
    calls = mock_cursor.execute.call_args_list
    sql_statements = [c[0][0] for c in calls]
    assert any("DELETE FROM documents WHERE period =" in sql for sql in sql_statements)
    assert any("DELETE FROM employee_payroll WHERE period =" in sql for sql in sql_statements)
    assert any("DELETE FROM payroll_events WHERE period =" in sql for sql in sql_statements)
    assert any("DELETE FROM validation_results WHERE period =" in sql for sql in sql_statements)
    mock_conn.commit.assert_called_once()


def test_get_documents_pg_fallback_when_s3_empty():
    # S3 is authoritative and read first; PostgreSQL is only a fallback when S3 has
    # nothing for the period.
    client = TestClient(app)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        ("inv.pdf", "invoice", "el", "2026-03-01", "Vendor A", "12345", None, "EUR", 100.0, 24.0, 24.0, 124.0, "REF1", 1.0, "upload1")
    ]

    with patch("services.storage.list_keys", return_value=[]), \
         patch("db.client.get_db_connection", return_value=mock_conn):
        resp = client.get("/api/documents/2026-03")

    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["source_file"] == "inv.pdf"
    assert docs[0]["total_amount"] == 124.0


def test_get_documents_fresh_s3_wins_over_stale_pg():
    # Regression for the data-loss bug: a freshly-uploaded document is written to S3
    # but NOT to PostgreSQL. get_documents MUST return the fresh S3 document, never
    # the stale PG mirror — otherwise the review screen hides the new upload and the
    # review PUT deletes it. If PG were consulted first this test would return "old".
    client = TestClient(app)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    # Stale PG mirror still holds only the OLD document.
    mock_cursor.fetchall.return_value = [
        ("old.pdf", "expense", "el", "2026-03-01", "Old Vendor", "1", None, "EUR", None, None, None, 90.0, "OLD", 1.0, "up-old")
    ]
    # Fresh S3 has the NEW uploaded document.
    fresh = {"documents": [{"source_file": "new.pdf", "doc_type": "invoice",
                            "total_amount": 10.0, "vendor_name": "Anthropic"}]}

    with patch("services.storage.list_keys",
               return_value=["extracted/2026-03/up-new/documents.json"]), \
         patch("services.storage.download_json", return_value=fresh), \
         patch("db.client.get_db_connection", return_value=mock_conn):
        resp = client.get("/api/documents/2026-03")

    assert resp.status_code == 200
    docs = resp.json()
    files = {d["source_file"] for d in docs}
    assert "new.pdf" in files, "fresh S3 upload must be returned"
    assert "old.pdf" not in files, "stale PG must NOT shadow the fresh S3 document"


def test_update_documents_db_success():
    client = TestClient(app)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    docs = [
        {
            "source_file": "inv.pdf",
            "doc_type": "invoice",
            "detected_language": "el",
            "issue_date": "2026-03-01",
            "vendor_name": "Vendor A",
            "vendor_tax_id": "12345",
            "recipient_name": None,
            "currency": "EUR",
            "subtotal": 100.0,
            "vat_amount": 24.0,
            "vat_rate_pct": 24.0,
            "total_amount": 124.0,
            "invoice_number": "REF1",
            "confidence": 1.0,
            "upload_id": "upload1"
        }
    ]
    
    with patch("db.client.get_db_connection", return_value=mock_conn), \
         patch("services.storage.list_keys", return_value=[]), \
         patch("services.storage.put_json", return_value="ok"):
        resp = client.put("/api/documents/2026-03", json={"documents": docs})
        
    assert resp.status_code == 200
    # SQL DELETE and INSERT should have been called
    calls = mock_cursor.execute.call_args_list
    sql_statements = [c[0][0] for c in calls]
    assert any("DELETE FROM documents WHERE period =" in sql for sql in sql_statements)
    assert any("INSERT INTO documents" in sql for sql in sql_statements)
    mock_conn.commit.assert_called_once()
