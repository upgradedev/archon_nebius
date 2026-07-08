"""
NarratorAgent — LLM executive summary with a deterministic fallback.
No network: the LLM call (`_call_llm`) is monkeypatched, or its OpenAI client is
a stub.
"""
from types import SimpleNamespace

import agents.narrator as narrator
from models.financial import (
    FinancialReport, MonthlyPnL, CashFlow, KeyMetrics, ExpenseCategory,
    PayrollEventSummary, EmployeeSummary, ValidationResult,
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


def _grounded_report() -> FinancialReport:
    """A report carrying every reconciliation stream the grounded prompt folds in."""
    rep = _report()
    rep.payrollEvents = [PayrollEventSummary(
        period="2026-01", company_name="Acme SA", net_total=10_000.0,
        gross_total=13_000.0, employer_cost_total=17_300.0, employee_count=4,
        bank_confirmed=True, validation_passed=True,
    )]
    rep.employeeSummaries = [EmployeeSummary(
        employee_code="E1", employee_name="Jo", period="2026-01",
        net_pay=2_500.0, gross_pay=3_250.0, employer_cost=4_325.0,
    )]
    rep.validationResults = [
        ValidationResult(rule="R1", passed=True, severity="info", message="ok", source_files=["b.pdf"]),
        ValidationResult(rule="R2", passed=False, severity="warning", message="ratio off", source_files=["r.pdf"]),
    ]
    return rep


def test_reconciliation_context_folds_in_every_stream():
    # _build_prompt -> _reconciliation_context must render the payroll multi-stream
    # block (employer cost vs bank net gap), cash flow, per-employee, and validation.
    prompt = narrator._build_prompt(_grounded_report())
    assert "Payroll multi-stream reconciliation (2026-01 for Acme SA)" in prompt
    assert "17,300.00" in prompt and "10,000.00" in prompt          # employer cost vs bank net
    assert "exceeds the bank transfer by €7,300.00 (73%)" in prompt  # the gap, computed
    assert "Employees covered: 4" in prompt
    assert "Cash flow (real movements)" in prompt
    assert "Per-employee payslip analytics available for 1 employee(s)" in prompt
    assert "R2: FAIL (warning)" in prompt and "R1: PASS" in prompt


def test_call_llm_invokes_client_and_returns_text():
    # Cover _call_llm directly with a stub OpenAI client (no network).
    captured = {}

    def create(model, messages, max_tokens, temperature):
        captured.update(model=model, max_tokens=max_tokens)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="  Executive summary.  "))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = narrator._call_llm(client, "test-model", "the prompt")
    assert out == "Executive summary."         # stripped
    assert captured["model"] == "test-model" and captured["max_tokens"] == 450
