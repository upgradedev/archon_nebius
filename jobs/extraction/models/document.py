from enum import Enum
from pydantic import BaseModel


class DocType(str, Enum):
    INVOICE = "invoice"
    PAYROLL = "payroll"
    EXPENSE = "expense"
    SALES = "sales"
    UNKNOWN = "unknown"


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    total: float


class ExtractedDocument(BaseModel):
    source_file: str
    doc_type: DocType
    detected_language: str          # e.g. "el" for Greek, "en" for English
    issue_date: str | None          # ISO 8601 date string
    vendor_name: str | None
    vendor_tax_id: str | None       # ΑΦΜ for Greek docs
    recipient_name: str | None
    currency: str                   # ISO 4217, e.g. "EUR"
    subtotal: float | None
    vat_amount: float | None
    vat_rate_pct: float | None
    total_amount: float
    line_items: list[LineItem]
    payment_due_date: str | None
    invoice_number: str | None
    notes: str | None
    raw_text_excerpt: str           # first 500 chars of extracted text for audit
    extraction_model: str
    confidence: float               # 0.0 – 1.0
