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
    subtotal: float | None
    vat_amount: float | None
    vat_rate_pct: float | None
    total_amount: float
    payment_due_date: str | None
    invoice_number: str | None
    notes: str | None
    confidence: float
    # Payroll-specific fields
    employee_count: int | None = None
    gross_pay_total: float | None = None
    employer_cost_total: float | None = None
    net_pay_total: float | None = None
    employee_name: str | None = None
    employee_code: str | None = None


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
    """Per-employee payroll analytics derived from payslip documents."""
    employee_code: str | None
    employee_name: str | None
    period: str
    net_pay: float
    gross_pay: float | None       # available when payroll_register is linked
    employer_cost: float | None   # gross + IKA; available from payroll_register


class PayrollEventSummary(BaseModel):
    """High-level summary of a linked payroll event for the dashboard."""
    period: str
    company_name: str | None
    net_total: float              # from bank_confirmation or sum of payslips
    gross_total: float | None     # from payroll_register
    employer_cost_total: float | None
    employee_count: int
    bank_confirmed: bool
    validation_passed: bool


class ValidationResult(BaseModel):
    rule: str
    passed: bool
    severity: str                 # "info" | "warning" | "error"
    message: str
    source_files: list[str]


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
    executiveSummary: str
