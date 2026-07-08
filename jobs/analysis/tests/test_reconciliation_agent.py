"""
ReconciliationAgent — vendor statement vs. uploaded invoices.
"Their statement says 4 invoices, we have 3 — find the missing one."
"""
from agents import reconciliation_agent


def _stmt(doc, **kw):
    return doc(doc_type="account_statement", **kw)


def test_no_statements_returns_empty(doc):
    assert reconciliation_agent.run("2026-01", [doc(doc_type="invoice")]) == []


def test_clean_reconciliation(doc):
    stmt = _stmt(
        doc, vendor_name="DEH", vendor_tax_id="EL999",
        statement_balance=300.0,
        statement_entries=[
            {"document_number": "A1", "original_amount": 100, "remaining_amount": 0},
            {"document_number": "A2", "original_amount": 200, "remaining_amount": 0},
        ],
    )
    inv1 = doc(source_file="i1.pdf", doc_type="invoice", vendor_tax_id="EL999",
               invoice_number="A1", total_amount=100)
    inv2 = doc(source_file="i2.pdf", doc_type="invoice", vendor_tax_id="EL999",
               invoice_number="A2", total_amount=200)
    rec = reconciliation_agent.run("2026-01", [stmt, inv1, inv2])[0]
    assert rec.reconciled is True
    assert rec.missing_in_system == []
    assert rec.discrepancy_eur == 0.0
    assert rec.uploaded_total == 300.0


def test_missing_invoice_detected(doc):
    stmt = _stmt(
        doc, vendor_name="OTE", vendor_tax_id="EL111",
        statement_balance=300.0,
        statement_entries=[
            {"doc_number": "B1", "amount": 100, "balance": 0},
            {"doc_number": "B2", "amount": 200, "balance": 200, "overdue": True},
        ],
    )
    inv = doc(source_file="i.pdf", doc_type="invoice", vendor_tax_id="EL111",
              invoice_number="B1", total_amount=100)
    rec = reconciliation_agent.run("2026-01", [stmt, inv])[0]
    assert rec.reconciled is False
    assert rec.missing_in_system == ["B2"]
    assert rec.discrepancy_eur == 200.0   # statement 300 - uploaded 100
    # alternate key names (doc_number/amount/balance/overdue) parsed
    assert any(e.is_overdue for e in rec.statement_entries)


def test_unmatched_upload_listed(doc):
    stmt = _stmt(doc, vendor_name="V", vendor_tax_id="EL222", statement_balance=100.0,
                 statement_entries=[{"document_number": "C1", "original_amount": 100, "remaining_amount": 0}])
    extra = doc(source_file="x.pdf", doc_type="invoice", vendor_tax_id="EL222",
                invoice_number="C9", total_amount=50)
    matched = doc(source_file="y.pdf", doc_type="invoice", vendor_tax_id="EL222",
                  invoice_number="C1", total_amount=100)
    rec = reconciliation_agent.run("2026-01", [stmt, extra, matched])[0]
    assert "C9" in rec.unmatched_uploads


def test_malformed_entry_skipped(doc):
    stmt = _stmt(doc, vendor_name="V", vendor_tax_id="EL333", statement_balance=0.0,
                 statement_entries=[
                     {"document_number": "OK", "original_amount": 100, "remaining_amount": 0},
                     {"document_number": "BAD", "original_amount": "not-a-number"},
                 ])
    rec = reconciliation_agent.run("2026-01", [stmt])[0]
    # only the valid entry survives
    nums = {e.document_number for e in rec.statement_entries}
    assert "OK" in nums and "BAD" not in nums


def test_vendor_matched_by_name_when_no_tax_id(doc):
    stmt = _stmt(doc, vendor_name="Acme", vendor_tax_id=None, statement_balance=100.0,
                 statement_entries=[{"document_number": "D1", "original_amount": 100, "remaining_amount": 0}])
    inv = doc(source_file="i.pdf", doc_type="invoice", vendor_name="Acme",
              vendor_tax_id=None, invoice_number="D1", total_amount=100)
    rec = reconciliation_agent.run("2026-01", [stmt, inv])[0]
    assert rec.reconciled is True
