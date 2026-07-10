from enum import Enum
from pydantic import BaseModel


class DocType(str, Enum):
    INVOICE = "invoice"                       # vendor/purchase invoice
    SALES = "sales"                           # sales invoice (company is the seller)
    EXPENSE = "expense"                       # expense receipt
    PAYROLL_REGISTER = "payroll_register"     # official payroll sheet (gross + social security + employer cost)
    BANK_CONFIRMATION = "bank_confirmation"   # bank batch payroll transfer confirmation (net total)
    PAYSLIP = "payslip"                       # individual employee pay slip (net per person)
    PAYROLL = "payroll"                       # generic payroll when subtype cannot be determined
    ACCOUNT_STATEMENT = "account_statement"   # vendor statement of account (AR aging / reconciliation use only)
    UNKNOWN = "unknown"


class VatTreatment(str, Enum):
    STANDARD = "standard"             # e.g. Greek 24% VAT
    REVERSE_CHARGE = "reverse_charge" # B2B cross-border EU services (0% billed)
    EXEMPT = "exempt"                 # legally VAT-exempt activity
    ZERO_RATE = "zero_rate"           # zero-rated supply (e.g. exports)
    NONE = "none"                     # no VAT applicable (B2C, non-EU)


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    total: float


class ExtractedDocument(BaseModel):
    source_file: str
    doc_type: DocType
    detected_language: str          # e.g. "el" for Greek, "en" for English
    issue_date: str | None = None          # ISO 8601 date string
    vendor_name: str | None = None
    vendor_tax_id: str | None = None       # National Tax ID
    recipient_name: str | None = None
    currency: str                   # ISO 4217 — normalised to EUR when possible
    original_currency: str | None = None   # as billed (e.g. "USD" for AWS/OpenAI)
    original_amount: float | None = None   # amount in original currency before FX conversion
    subtotal: float | None = None
    vat_amount: float | None = None
    vat_rate_pct: float | None = None
    vat_treatment: VatTreatment | None = None  # classification of VAT handling
    total_amount: float             # EUR-normalised total
    line_items: list[LineItem]
    payment_due_date: str | None = None
    invoice_number: str | None = None
    notes: str | None = None
    raw_text_excerpt: str           # first 500 chars of extracted text for audit
    extraction_model: str
    confidence: float               # 0.0 - 1.0

    # Payroll-specific fields (populated for payroll_register / bank_confirmation / payslip)
    employee_count: int | None = None
    gross_pay_total: float | None = None       # total gross wages (payroll_register)
    employer_cost_total: float | None = None   # gross + employer social-security share (payroll_register)
    net_pay_total: float | None = None         # total net transfers (bank_confirmation)
    employee_name: str | None = None           # for payslip docs
    employee_code: str | None = None           # internal employee code (payslip)

    # Account statement fields (populated for account_statement docs only)
    statement_balance: float | None = None     # closing balance per statement
    statement_overdue: float | None = None     # overdue amount per statement
    statement_entries: list[dict] | None = None  # raw invoice references from statement

    # Advisory prompt-injection scan over this document's extracted field values.
    # Populated by the extraction pipeline (injection_scan.scan_document). Shape:
    # {"detected": bool, "count": int, "matches": [{field, pattern, snippet}]}.
    # ADVISORY ONLY — surfaces what the extractor's DATA-not-instructions fence
    # already neutralized; it never changes extraction or validation outcomes.
    injection_scan: dict | None = None
