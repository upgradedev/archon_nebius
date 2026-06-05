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


class FinancialReport(BaseModel):
    period: str
    pnl: MonthlyPnL
    cashFlow: CashFlow
    expenseBreakdown: list[ExpenseCategory]
    topVendors: list[VendorSummary]
    keyMetrics: KeyMetrics
    executiveSummary: str
