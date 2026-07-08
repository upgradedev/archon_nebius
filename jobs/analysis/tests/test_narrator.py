"""
NarratorAgent — LLM executive summary with a deterministic fallback.
No network: the LLM call (`_call_llm`) is monkeypatched.
"""
import agents.narrator as narrator
from models.financial import (
    FinancialReport, MonthlyPnL, CashFlow, KeyMetrics, ExpenseCategory,
)


def _report() -> FinancialReport:
    return FinancialReport(
        period="2026-01",
        pnl=MonthlyPnL(period="2026-01", revenue=20000, expenses=12800,
                       netProfit=7200, grossMarginPct=36.0, operatingMarginPct=36.0),
        cashFlow=CashFlow(period="2026-01", operating=7000, investing=0, financing=0, net=7000),
        expenseBreakdown=[ExpenseCategory(category="Payroll", amount=12800, percentage=100.0, monthOverMonthPct=0.0)],
        topVendors=[],
        keyMetrics=KeyMetrics(revenueGrowthPct=0.0, expenseRatioPct=64.0, cashBurnRate=426.0,
                              invoiceCount=3, avgInvoiceValue=6666.0, collectionRatePct=95.0),
        payrollEvents=[], employeeSummaries=[], validationResults=[],
        vendorReconciliations=[], executiveSummary="",
    )


def test_narrator_returns_llm_text(monkeypatch):
    monkeypatch.setattr(narrator, "_call_llm", lambda *a, **k: "Strong month: profit up.")
    assert narrator.build_summary(_report()) == "Strong month: profit up."


def test_narrator_falls_back_on_llm_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("upstream 503")
    monkeypatch.setattr(narrator, "_call_llm", boom)
    out = narrator.build_summary(_report())
    assert "2026-01" in out
    assert "LLM error" in out
    assert "20,000.00" in out   # revenue formatted into the deterministic fallback
