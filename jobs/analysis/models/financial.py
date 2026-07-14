from pydantic import BaseModel


class ExtractedDoc(BaseModel):
    # ADR-006: every optional field carries an explicit default. Pydantic v2 treats
    # `x: T | None` WITHOUT a default as REQUIRED (accepts None but must be present),
    # so a document written by an older/leaner extraction schema that omits any of
    # these keys fails validation and `_load_documents` silently DROPS it. That bug
    # discarded 13 of 20 real documents on a live period (all revenue + most
    # expenses), zeroing the P&L. Defaults make the loader tolerant to schema drift.
    source_file: str
    doc_type: str
    detected_language: str = "unknown"
    issue_date: str | None = None
    vendor_name: str | None = None
    vendor_tax_id: str | None = None
    recipient_name: str | None = None
    currency: str = "EUR"
    original_currency: str | None = None
    original_amount: float | None = None
    subtotal: float | None = None
    vat_amount: float | None = None
    vat_rate_pct: float | None = None
    vat_treatment: str | None = None
    total_amount: float = 0.0
    payment_due_date: str | None = None
    invoice_number: str | None = None
    notes: str | None = None
    confidence: float = 0.0
    # Payroll-specific
    employee_count: int | None = None
    gross_pay_total: float | None = None
    employer_cost_total: float | None = None
    net_pay_total: float | None = None
    employee_name: str | None = None
    employee_code: str | None = None
    # Statement-specific
    statement_balance: float | None = None
    statement_overdue: float | None = None
    statement_entries: list[dict] | None = None


class MonthlyPnL(BaseModel):
    period: str
    revenue: float
    expenses: float
    netProfit: float
    grossMarginPct: float
    operatingMarginPct: float


class CashFlow(BaseModel):
    period: str
    operating: float
    investing: float
    financing: float
    net: float


class ExpenseCategory(BaseModel):
    category: str
    amount: float
    percentage: float
    monthOverMonthPct: float


class VendorSummary(BaseModel):
    name: str
    totalAmount: float
    invoiceCount: int
    avgDaysToPay: int


class KeyMetrics(BaseModel):
    # revenueGrowthPct needs a prior period and collectionRatePct needs A/R aging /
    # payment data — neither is available in a single-period run, so they are None
    # (rendered as N/A) rather than a fabricated constant. Honesty over a fake KPI.
    revenueGrowthPct: float | None = None
    expenseRatioPct: float
    cashBurnRate: float
    invoiceCount: int
    avgInvoiceValue: float
    collectionRatePct: float | None = None


class EmployeeSummary(BaseModel):
    employee_code: str | None
    employee_name: str | None
    period: str
    net_pay: float
    gross_pay: float | None
    employer_cost: float | None


class PayrollEventSummary(BaseModel):
    period: str
    company_name: str | None
    net_total: float
    gross_total: float | None
    employer_cost_total: float | None
    employee_count: int
    bank_confirmed: bool
    validation_passed: bool


class ValidationResult(BaseModel):
    rule: str
    passed: bool
    severity: str
    message: str
    source_files: list[str]


# ── Vendor reconciliation models ─────────────────────────────────────────────

class StatementEntry(BaseModel):
    """One line from a vendor Statement of Account."""
    document_number: str | None     # invoice / credit note number per vendor
    posting_date: str | None        # date per statement
    due_date: str | None
    original_amount: float
    remaining_amount: float
    is_overdue: bool


class VendorReconciliation(BaseModel):
    """
    Comparison between what the vendor's statement says and what invoices
    we actually have in the system. Surfaces missing documents.
    """
    vendor_name: str
    vendor_tax_id: str | None
    period: str

    # What vendor says (from account_statement doc)
    statement_balance: float | None
    statement_overdue: float | None
    statement_entries: list[StatementEntry]

    # What we have in our system (uploaded invoices)
    uploaded_invoices: list[str]        # invoice_number of matched docs
    uploaded_total: float

    # Discrepancy analysis
    missing_in_system: list[str]        # doc numbers in statement not found as uploads
    unmatched_uploads: list[str]        # uploaded invoice numbers with no statement reference
    reconciled: bool                    # True when all statement entries matched
    discrepancy_eur: float              # statement_balance - uploaded_total (0 = clean)


# ── Main report ───────────────────────────────────────────────────────────────

class FinancialReport(BaseModel):
    period: str
    pnl: MonthlyPnL
    cashFlow: CashFlow
    expenseBreakdown: list[ExpenseCategory]
    topVendors: list[VendorSummary]
    keyMetrics: KeyMetrics
    payrollEvents: list[PayrollEventSummary]
    employeeSummaries: list[EmployeeSummary]
    validationResults: list[ValidationResult]
    vendorReconciliations: list[VendorReconciliation]
    executiveSummary: str
