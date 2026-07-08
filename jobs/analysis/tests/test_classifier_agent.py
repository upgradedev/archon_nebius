"""Analysis-tier ClassifierAgent — keyword recovery of misclassified docs."""
from agents.classifier import classify


def test_unknown_with_payroll_keyword_becomes_payroll(doc):
    out = classify([doc(doc_type="unknown", vendor_name="X", notes="Μισθοδοσία Ιανουαρίου")])
    assert out[0].doc_type == "payroll"


def test_unknown_without_vendor_stays_unknown(doc):
    out = classify([doc(doc_type="unknown", vendor_name=None, notes="salary payroll")])
    assert out[0].doc_type == "unknown"


def test_invoice_with_sales_keyword_becomes_sales(doc):
    out = classify([doc(doc_type="invoice", total_amount=500, notes="Τιμολόγιο πώλησης")])
    assert out[0].doc_type == "sales"


def test_invoice_without_sales_keyword_unchanged(doc):
    out = classify([doc(doc_type="invoice", total_amount=500, notes="purchase")])
    assert out[0].doc_type == "invoice"


def test_known_types_untouched(doc):
    out = classify([doc(doc_type="expense", notes="μισθος")])
    assert out[0].doc_type == "expense"
