"""
PnLAgent — aggregates extracted documents into P&L metrics.

Single responsibility: pure Python arithmetic over classified documents.
No LLM call; deterministic and fast.

Uses employer_cost_total from payroll_register documents (when available)
as the authoritative payroll expense figure — not the bank net transfer —
to capture the full employer cost including IKA contributions.
"""

from collections import defaultdict
from models.financial import (
    ExtractedDoc, MonthlyPnL, ExpenseCategory, VendorSummary, KeyMetrics,
)

EXPENSE_DOC_TYPES = {"invoice", "expense", "payroll", "payroll_register",
                     "bank_confirmation", "payslip"}
REVENUE_DOC_TYPES = {"sales"}
PAYROLL_TYPES = {"payroll_register", "bank_confirmation", "payslip", "payroll"}


def build_pnl(period: str, docs: list[ExtractedDoc]) -> MonthlyPnL:
    revenue = sum(d.total_amount for d in docs if d.doc_type in REVENUE_DOC_TYPES)
    expenses = _compute_expenses(docs)
    net_profit = revenue - expenses
    gross_margin = (net_profit / revenue * 100) if revenue else 0.0

    return MonthlyPnL(
        period=period,
        revenue=round(revenue, 2),
        expenses=round(expenses, 2),
        netProfit=round(net_profit, 2),
        grossMarginPct=round(gross_margin, 2),
        operatingMarginPct=round(gross_margin, 2),  # simplified; extend with D&A when available
    )


def build_expense_breakdown(docs: list[ExtractedDoc]) -> list[ExpenseCategory]:
    totals: dict[str, float] = defaultdict(float)
    for doc in docs:
        if doc.doc_type in EXPENSE_DOC_TYPES:
            cat = _categorise(doc)
            totals[cat] += _effective_amount(doc)

    grand_total = sum(totals.values()) or 1.0
    return [
        ExpenseCategory(
            category=cat,
            amount=round(amt, 2),
            percentage=round(amt / grand_total * 100, 1),
            monthOverMonthPct=0.0,
        )
        for cat, amt in sorted(totals.items(), key=lambda x: x[1], reverse=True)
    ]


def build_vendor_summary(docs: list[ExtractedDoc]) -> list[VendorSummary]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for doc in docs:
        if doc.doc_type in EXPENSE_DOC_TYPES and doc.vendor_name:
            totals[doc.vendor_name] += doc.total_amount
            counts[doc.vendor_name] += 1

    return [
        VendorSummary(
            name=name,
            totalAmount=round(amt, 2),
            invoiceCount=counts[name],
            avgDaysToPay=30,
        )
        for name, amt in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
    ]


def build_key_metrics(docs: list[ExtractedDoc], revenue: float, expenses: float) -> KeyMetrics:
    invoices = [d for d in docs if d.doc_type == "sales"]
    invoice_count = len(invoices)
    avg_invoice = (sum(d.total_amount for d in invoices) / invoice_count) if invoice_count else 0.0

    return KeyMetrics(
        revenueGrowthPct=0.0,
        expenseRatioPct=round(expenses / revenue * 100, 1) if revenue else 0.0,
        cashBurnRate=round(expenses / 30, 2),
        invoiceCount=invoice_count,
        avgInvoiceValue=round(avg_invoice, 2),
        collectionRatePct=95.0,
    )


# ── internal helpers ──────────────────────────────────────────────────────────

def _compute_expenses(docs: list[ExtractedDoc]) -> float:
    """
    Use employer_cost_total from payroll_register as the true payroll cost.
    For all other expense docs use total_amount directly.
    De-duplicate payroll: if a register is present, skip bank_confirmation
    and payslips for the same period to avoid double-counting.
    """
    has_register = any(d.doc_type == "payroll_register" for d in docs)
    total = 0.0
    for doc in docs:
        if doc.doc_type in REVENUE_DOC_TYPES:
            continue
        if doc.doc_type == "payroll_register":
            # prefer employer_cost_total (includes IKA); fall back to total_amount
            total += doc.employer_cost_total or doc.total_amount
        elif doc.doc_type in ("bank_confirmation", "payslip") and has_register:
            continue  # already counted via register
        elif doc.doc_type in EXPENSE_DOC_TYPES:
            total += doc.total_amount
    return total


def _effective_amount(doc: ExtractedDoc) -> float:
    if doc.doc_type == "payroll_register":
        return doc.employer_cost_total or doc.total_amount
    return doc.total_amount


def _categorise(doc: ExtractedDoc) -> str:
    if doc.doc_type in ("payroll_register", "payroll", "payslip", "bank_confirmation"):
        return "Payroll"
    text = ((doc.notes or "") + " " + (doc.vendor_name or "")).lower()
    if any(k in text for k in ["ενοίκιο", "rent", "lease"]):
        return "Rent & Facilities"
    if any(k in text for k in ["ηλεκτρ", "electric", "power", "gas", "water", "utility"]):
        return "Utilities"
    if any(k in text for k in ["software", "saas", "cloud", "subscription"]):
        return "Software & Cloud"
    if any(k in text for k in ["marketing", "advertising", "διαφήμιση"]):
        return "Marketing"
    return "Operating Expenses"
