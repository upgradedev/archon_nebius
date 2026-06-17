"""
P&L builder agent — aggregates extracted documents into financial metrics.
Pure Python arithmetic; LLM is not involved in number crunching.
"""

from collections import defaultdict
from models.financial import ExtractedDoc, FinancialReport, MonthlyPnL, CashFlow, ExpenseCategory, VendorSummary, KeyMetrics


EXPENSE_DOC_TYPES = {"invoice", "expense", "payroll"}
REVENUE_DOC_TYPES = {"sales"}


def build_report(period: str, docs: list[ExtractedDoc]) -> FinancialReport:
    revenue = sum(d.total_amount for d in docs if d.doc_type in REVENUE_DOC_TYPES)
    expenses = sum(d.total_amount for d in docs if d.doc_type in EXPENSE_DOC_TYPES)
    net_profit = revenue - expenses
    gross_margin = (net_profit / revenue * 100) if revenue else 0.0
    operating_margin = gross_margin  # simplified; extend with EBIT if needed

    pnl = MonthlyPnL(
        period=period,
        revenue=round(revenue, 2),
        expenses=round(expenses, 2),
        netProfit=round(net_profit, 2),
        grossMarginPct=round(gross_margin, 2),
        operatingMarginPct=round(operating_margin, 2),
    )

    cash_flow = CashFlow(
        period=period,
        operating=round(net_profit * 0.9, 2),   # simplified proxy
        investing=0.0,
        financing=0.0,
        net=round(net_profit * 0.9, 2),
    )

    expense_breakdown = _build_expense_breakdown(docs)
    top_vendors = _build_vendor_summary(docs)
    key_metrics = _build_key_metrics(docs, revenue, expenses)

    return FinancialReport(
        period=period,
        pnl=pnl,
        cashFlow=cash_flow,
        expenseBreakdown=expense_breakdown,
        topVendors=top_vendors,
        keyMetrics=key_metrics,
        executiveSummary="",  # filled by narrator
    )


def _build_expense_breakdown(docs: list[ExtractedDoc]) -> list[ExpenseCategory]:
    totals: dict[str, float] = defaultdict(float)
    for doc in docs:
        if doc.doc_type in EXPENSE_DOC_TYPES:
            cat = _categorise(doc)
            totals[cat] += doc.total_amount

    grand_total = sum(totals.values()) or 1.0
    return [
        ExpenseCategory(
            category=cat,
            amount=round(amt, 2),
            percentage=round(amt / grand_total * 100, 1),
            monthOverMonthPct=0.0,  # requires historical data
        )
        for cat, amt in sorted(totals.items(), key=lambda x: x[1], reverse=True)
    ]


def _build_vendor_summary(docs: list[ExtractedDoc]) -> list[VendorSummary]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for doc in docs:
        if doc.doc_type in EXPENSE_DOC_TYPES and doc.vendor_name:
            totals[doc.vendor_name] += doc.total_amount
            counts[doc.vendor_name] += 1

    vendors = [
        VendorSummary(
            name=name,
            totalAmount=round(amt, 2),
            invoiceCount=counts[name],
            avgDaysToPay=30,  # placeholder — requires payment date tracking
        )
        for name, amt in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
    ]
    return vendors


def _build_key_metrics(docs: list[ExtractedDoc], revenue: float, expenses: float) -> KeyMetrics:
    invoices = [d for d in docs if d.doc_type == "sales"]
    invoice_count = len(invoices)
    avg_invoice = (sum(d.total_amount for d in invoices) / invoice_count) if invoice_count else 0.0

    return KeyMetrics(
        revenueGrowthPct=0.0,       # requires prior period
        expenseRatioPct=round(expenses / revenue * 100, 1) if revenue else 0.0,
        cashBurnRate=round(expenses / 30, 2),   # daily burn
        invoiceCount=invoice_count,
        avgInvoiceValue=round(avg_invoice, 2),
        collectionRatePct=95.0,     # placeholder — requires AR aging data
    )


def _categorise(doc: ExtractedDoc) -> str:
    if doc.doc_type == "payroll":
        return "Payroll"
    notes_lower = (doc.notes or "").lower()
    vendor_lower = (doc.vendor_name or "").lower()
    if any(k in notes_lower or k in vendor_lower for k in ["ενοίκιο", "rent", "lease"]):
        return "Rent & Facilities"
    if any(k in notes_lower or k in vendor_lower for k in ["ηλεκτρ", "electric", "power", "gas", "water", "utility"]):
        return "Utilities"
    if any(k in notes_lower or k in vendor_lower for k in ["software", "saas", "cloud", "subscription"]):
        return "Software & Cloud"
    if any(k in notes_lower or k in vendor_lower for k in ["marketing", "advertising", "διαφήμιση"]):
        return "Marketing"
    return "Operating Expenses"
