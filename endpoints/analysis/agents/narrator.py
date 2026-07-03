"""
Executive narrator — uses an LLM to write a concise English executive summary
from the computed financial metrics.

Grounded-narrator tier: the prompt is enriched with a multi-stream
reconciliation context block (payroll bank-transfer net vs true employer cost,
cash flow, per-employee analytics, cross-document validation results) so the
summary reasons over the fused financial picture rather than top-line numbers
alone. The model is instructed to end with a "Sources:" line that cites the
actual input documents / payroll events / validation rules it drew from —
traceability over the real inputs, not an external corpus.
"""

import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from models.financial import FinancialReport


def build_summary(report: FinancialReport) -> str:
    client = OpenAI(
        base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
        api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
    )
    model = os.getenv("ANALYSIS_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

    prompt = _build_prompt(report)

    try:
        return _call_llm(client, model, prompt)
    except Exception as exc:
        import logging
        logging.getLogger("archon.analysis").warning("Narrator LLM failed (non-fatal): %s", exc)
        return (
            f"Financial summary for {report.period}: Revenue €{report.pnl.revenue:,.2f}, "
            f"Expenses €{report.pnl.expenses:,.2f}, Net Profit €{report.pnl.netProfit:,.2f}. "
            f"(Executive narrative unavailable — LLM error)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(report: FinancialReport) -> str:
    top_categories = ", ".join(e.category for e in report.expenseBreakdown[:3])
    reconciliation = _reconciliation_context(report)

    return f"""You are a CFO-level financial analyst. Write a concise executive summary (3-4 sentences, plain English, no bullet points) for the following monthly financial data.

Where relevant, note where correlating multiple document streams was essential to arriving at the correct figure — a single payroll period is understood from several documents at once (a bank confirmation shows only the employee net transfer, while the payroll register adds employer social-insurance contributions, and separate tax-authority withholdings form a further stream). You may reference applicable universal accounting standards for context (e.g. IAS 1 presentation of financial statements, IAS 19 employee-benefit cost), but every citation you list must be grounded in the actual inputs below.

Period: {report.period}
Revenue: €{report.pnl.revenue:,.2f}
Expenses: €{report.pnl.expenses:,.2f}
Net Profit: €{report.pnl.netProfit:,.2f}
Gross Margin: {report.pnl.grossMarginPct:.1f}%
Operating Margin: {report.pnl.operatingMarginPct:.1f}%
Revenue Growth MoM: {report.keyMetrics.revenueGrowthPct:.1f}%
Expense Ratio: {report.keyMetrics.expenseRatioPct:.1f}%
Invoice Count: {report.keyMetrics.invoiceCount}
Avg Invoice Value: €{report.keyMetrics.avgInvoiceValue:,.2f}
Collection Rate: {report.keyMetrics.collectionRatePct:.1f}%
Top Expense Categories: {top_categories}{reconciliation}

Write the summary now. After the summary, output a blank line, then a single line that begins exactly with "Sources: " and lists the specific inputs you drew from — payroll registers/periods, bank confirmations, validation rules, or accounting standards — separated by " · " (space, middle-dot, space). Example: "Sources: payroll register 2026-01 · bank confirmation · validation R1 · IAS 19". Only cite inputs that appear in the data above."""


def _reconciliation_context(report: FinancialReport) -> str:
    """
    Build a multi-stream reconciliation context block from the fused report.

    Feeds the narrator the payroll bank-net vs true employer-cost gap, cash flow,
    per-employee coverage, and validation results so the summary reasons over the
    correlated picture. Returns "" when no supporting streams are present so the
    prompt degrades gracefully (and the deterministic unit tests stay green).
    """
    lines: list[str] = []

    for ev in report.payrollEvents:
        if ev.employer_cost_total and ev.net_total:
            gap = ev.employer_cost_total - ev.net_total
            gap_pct = (gap / ev.net_total * 100) if ev.net_total else 0.0
            company = f" for {ev.company_name}" if ev.company_name else ""
            lines.append(
                f"\nPayroll multi-stream reconciliation ({ev.period}{company}):"
                f"\n  • Bank confirmation (employee net transfers): €{ev.net_total:,.2f}"
                f"\n  • Payroll register (gross + employer social-insurance cost): €{ev.employer_cost_total:,.2f}"
                f"\n  • True employer cost exceeds the bank transfer by €{gap:,.2f} ({gap_pct:.0f}%)."
                f"\n  Employer social-insurance contributions and tax-authority withholdings"
                f"\n  are separate payment streams not visible in the bank slip; accurate P&L"
                f"\n  requires correlating all of them. Employees covered: {ev.employee_count}."
                f"\n  Bank-confirmed: {'yes' if ev.bank_confirmed else 'no'}."
            )
            break

    if report.cashFlow:
        cf = report.cashFlow
        lines.append(
            f"\nCash flow (real movements): operating €{cf.operating:,.2f}, "
            f"investing €{cf.investing:,.2f}, financing €{cf.financing:,.2f}, "
            f"net €{cf.net:,.2f}."
        )

    if report.employeeSummaries:
        lines.append(
            f"\nPer-employee payslip analytics available for "
            f"{len(report.employeeSummaries)} employee(s)."
        )

    if report.validationResults:
        rendered = []
        for v in report.validationResults[:6]:
            status = "PASS" if v.passed else f"FAIL ({v.severity})"
            rendered.append(f"{v.rule}: {status} — {v.message}")
        lines.append(
            "\nCross-document validation results:\n  " + "\n  ".join(rendered)
        )

    return "".join(lines)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _call_llm(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=450,
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()
