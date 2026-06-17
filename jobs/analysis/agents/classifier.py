"""
Classifier agent — validates and re-classifies extracted documents.
Ensures doc_type is correct before P&L aggregation.
"""

from models.financial import ExtractedDoc


def classify(docs: list[ExtractedDoc]) -> list[ExtractedDoc]:
    """
    Rule-based post-processing on top of LLM extraction.
    Catches common misclassifications using amount patterns and keywords.
    """
    for doc in docs:
        # Payroll docs typically have many equal line items (salaries)
        if doc.doc_type == "unknown" and doc.vendor_name and _is_likely_payroll(doc):
            doc.doc_type = "payroll"
        # Sales invoices have the company as vendor
        if doc.doc_type == "invoice" and doc.total_amount > 0 and _is_sales(doc):
            doc.doc_type = "sales"
    return docs


def _is_likely_payroll(doc: ExtractedDoc) -> bool:
    keywords = {"μισθός", "μισθοδοσία", "salary", "payroll", "εργαζόμενος", "payslip"}
    text = (doc.notes or "").lower()
    return any(k in text for k in keywords)


def _is_sales(doc: ExtractedDoc) -> bool:
    keywords = {"τιμολόγιο πώλησης", "sales invoice", "πώληση"}
    text = (doc.notes or "").lower()
    return any(k in text for k in keywords)
