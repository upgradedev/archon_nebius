"""
ClassifierAgent — validates and enriches doc_type after LLM extraction.

Single responsibility: ensure doc_type is correct before downstream agents.
All rules are deterministic (no LLM call) — fast, auditable, zero cost.

Distinguishes the three payroll document subtypes that represent the same
payroll event from different perspectives:
  - bank_confirmation  : bank batch payment confirmation (net total only)
  - payroll_register   : official payroll sheet (gross + IKA + employer cost)
  - payslip            : individual employee pay slip (net per person)
"""

from models.document import ExtractedDocument, DocType


def run(docs: list[ExtractedDocument]) -> list[ExtractedDocument]:
    """Reclassify documents where extraction produced an incorrect or generic type."""
    for doc in docs:
        if doc.doc_type in (DocType.UNKNOWN, DocType.PAYROLL):
            doc.doc_type = _infer_type(doc)
    return docs


# ── keyword sets ─────────────────────────────────────────────────────────────

_BANK_CONFIRMATION_KW = {
    "eurobank", "alpha bank", "πειραιωσ", "εθνικη", "τραπεζα",
    "payroll transfer", "batch payment", "μαζικη πληρωμη",
    "εντολη μεταφορας", "βεβαιωση μεταφορας", "κατασταση εμβασματων",
}

_PAYROLL_REGISTER_KW = {
    "μισθοδοτικη κατασταση", "payroll register", "κατασταση μισθοδοσιας",
    "συνολικο κοστος εργοδοτη", "ika", "ικα", "εφκα",
    "ασφαλιστικες εισφορες", "εισφορες εργοδοτη", "αναλυτικη κατασταση",
}

_PAYSLIP_KW = {
    "αποδειξη πληρωμης", "payslip", "pay slip",
    "αναλυτικο εκκαθαριστικο", "εκκαθαριστικο μισθοδοσιας",
}

_PAYROLL_GENERIC_KW = {"payroll", "μισθοδοσια", "salary", "μισθος"}
_SALES_KW = {"τιμολογιο πωλησης", "sales invoice", "πωληση"}


def _search_text(doc: ExtractedDocument) -> str:
    """Return a single normalised string covering all text fields."""
    import unicodedata

    def _norm(s: str) -> str:
        # strip accents so Greek keyword matching is accent-insensitive
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

    parts = [doc.notes or "", doc.vendor_name or "", doc.raw_text_excerpt or ""]
    return _norm(" ".join(parts))


def _infer_type(doc: ExtractedDocument) -> DocType:
    text = _search_text(doc)
    if any(k in text for k in _BANK_CONFIRMATION_KW):
        return DocType.BANK_CONFIRMATION
    if any(k in text for k in _PAYROLL_REGISTER_KW):
        return DocType.PAYROLL_REGISTER
    if any(k in text for k in _PAYSLIP_KW):
        return DocType.PAYSLIP
    if any(k in text for k in _PAYROLL_GENERIC_KW):
        return DocType.PAYROLL   # keep generic when subtype indeterminate
    if any(k in text for k in _SALES_KW):
        return DocType.SALES
    return DocType.UNKNOWN
