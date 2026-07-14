"""ExtractedDoc must tolerate documents written by a leaner/older extraction schema
(ADR-006). A doc that omits optional fields must still parse — otherwise
_load_documents silently drops it and the P&L is understated. Regression guard for
the bug where 13 of 20 live documents (all revenue + most expenses) were skipped,
zeroing revenue."""
from models.financial import ExtractedDoc


# The minimal shape an older extraction wrote: core fields only, none of the
# richer VAT / language / notes / tax-id fields the current pipeline adds.
_MINIMAL = {
    "source_file": "sales_northwind_202601.pdf",
    "doc_type": "sales",
    "vendor_name": "Northwind Trading Ltd",
    "currency": "EUR",
    "total_amount": 34200.0,
    "invoice_number": "INV-1",
    "issue_date": "2026-01-15",
}


def test_minimal_document_parses():
    doc = ExtractedDoc(**_MINIMAL)
    assert doc.total_amount == 34200.0
    assert doc.doc_type == "sales"
    # Omitted optionals default, they do not raise.
    assert doc.detected_language == "unknown"
    assert doc.subtotal is None
    assert doc.vat_amount is None
    assert doc.notes is None
    assert doc.vendor_tax_id is None


def test_bare_document_parses_with_amount_default():
    # Even a doc with only the two truly-required fields must not raise.
    doc = ExtractedDoc(source_file="x.pdf", doc_type="invoice")
    assert doc.total_amount == 0.0
    assert doc.currency == "EUR"


def test_full_document_still_parses():
    full = dict(_MINIMAL, detected_language="en", vendor_tax_id="EL123",
                recipient_name="Us Ltd", subtotal=30000.0, vat_amount=4200.0,
                vat_rate_pct=14.0, payment_due_date="2026-02-15",
                notes="paid", confidence=0.98)
    doc = ExtractedDoc(**full)
    assert doc.vat_amount == 4200.0 and doc.confidence == 0.98
