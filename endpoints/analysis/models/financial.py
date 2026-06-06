from pydantic import BaseModel


class ExtractedDoc(BaseModel):
    source_file: str
    doc_type: str
    detected_language: str
    issue_date: str | None
    vendor_name: str | None
    vendor_tax_id: str | None
    recipient_name: str | None
    currency: str
    original_currency: str | None = None
    original_amount: float | None = None
    subtotal: float | None
    vat_amount: float | None
    vat_rate_pct: float | None
    vat_treatment: str | None = None
    total_amount: float
    payment_due_date: str | None
    invoice_number: str | None
    notes: str | None
    confidence: float
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
    revenueGrowthPct: float
    expenseRatioPct: float
    cashBurnRate: float
    invoiceCount: int
    avgInvoiceValue: float
    collectionRatePct: float


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
