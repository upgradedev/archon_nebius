"""
PnLAgent — aggregates extracted documents into P&L metrics.

Single responsibility: pure Python arithmetic over classified documents.
No LLM call; deterministic and fast.

Uses `employer_cost_total` reported by a payroll register (when available) as
the payroll expense figure, rather than double-counting the register, bank
confirmation, and payslips.
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
    for doc in _expense_docs(docs):
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
        # A supplier ranking comes from purchase/expense documents. Payroll,
        # bank confirmations, sales, and reference statements are not supplier
        # spend and would otherwise rank the company or bank as a vendor.
        if doc.doc_type in {"invoice", "expense"} and doc.vendor_name:
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


_INVOICE_DOC_TYPES = {"invoice", "sales", "expense"}


def build_key_metrics(docs: list[ExtractedDoc], revenue: float, expenses: float) -> KeyMetrics:
    # "Invoices" counts every invoice document (sales AND purchase/expense), not only
    # sales — an uploaded expense invoice must register, otherwise the tile reads 0.
    invoices = [d for d in docs if d.doc_type in _INVOICE_DOC_TYPES]
    invoice_count = len(invoices)
    avg_invoice = (sum(d.total_amount for d in invoices) / invoice_count) if invoice_count else 0.0

    return KeyMetrics(
        # No prior period / no A/R aging in a single-period run → report None (N/A),
        # never a fabricated growth or collection figure.
        revenueGrowthPct=None,
        expenseRatioPct=round(expenses / revenue * 100, 1) if revenue else 0.0,
        cashBurnRate=round(expenses / 30, 2),
        invoiceCount=invoice_count,
        avgInvoiceValue=round(avg_invoice, 2),
        collectionRatePct=None,
    )


# ── internal helpers ──────────────────────────────────────────────────────────

def _compute_expenses(docs: list[ExtractedDoc]) -> float:
    """
    Use employer_cost_total from payroll_register as the register-reported employer cost.
    For all other expense docs use total_amount directly.
    De-duplicate payroll: if a register is present, skip bank_confirmation
    and payslips for the same period to avoid double-counting.
    """
    return sum(_effective_amount(doc) for doc in _expense_docs(docs))


def _expense_docs(docs: list[ExtractedDoc]) -> list[ExtractedDoc]:
    """Choose the same non-duplicated expense sources for every P&L view."""
    has_register = any(d.doc_type == "payroll_register" for d in docs)
    return [
        doc
        for doc in docs
        if doc.doc_type in EXPENSE_DOC_TYPES
        and not (
            has_register
            and doc.doc_type in ("bank_confirmation", "payslip")
        )
    ]


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
