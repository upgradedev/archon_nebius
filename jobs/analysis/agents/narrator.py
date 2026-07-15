"""
Executive narrator — uses an LLM to write a concise English executive summary
from the computed financial metrics.

Grounded-narrator tier: the prompt is enriched with a document-comparison
context block (bank-confirmed payroll net vs register-reported employer cost,
the assumption-based cash-flow view, per-employee analytics, and named payroll
checks). The prompt explicitly prevents the narrator from turning those checks
into claims about tax remittance or generic payment matching.
"""

import os

import httpx
from openai import OpenAI, APIConnectionError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from models.financial import FinancialReport


def build_summary(report: FinancialReport) -> str:
    client = OpenAI(
        base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
        api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
        timeout=30.0,
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
    # These are None when not derivable from a single period; render N/A so the
    # narrator is told the truth instead of a fabricated number.
    km = report.keyMetrics
    growth = f"{km.revenueGrowthPct:.1f}%" if km.revenueGrowthPct is not None else "N/A (single period)"
    collection = f"{km.collectionRatePct:.1f}%" if km.collectionRatePct is not None else "N/A (no A/R aging data)"

    return f"""You are a CFO-level financial analyst. Write a concise executive summary (3-4 sentences, plain English, no bullet points) for the following monthly financial data.

Where relevant, explain that a bank confirmation, payroll register, and payslips report different payroll measures. Use the register-reported employer cost for the P&L and the bank-confirmed net transfer for the current cash-flow view. Do not claim that Archon verified separate tax or social-insurance remittances, generic bank-to-invoice payment matching, collections, or duplicate payments: those checks are not present in the data below. Do not call a figure "true" or "fully reconciled" when it is only reported by one uploaded document.

Period: {report.period}
Revenue: €{report.pnl.revenue:,.2f}
Expenses: €{report.pnl.expenses:,.2f}
Net Profit: €{report.pnl.netProfit:,.2f}
Simplified document margin (net profit / document-total revenue): {report.pnl.operatingMarginPct:.1f}%
Revenue Growth MoM: {growth}
Expense Ratio: {report.keyMetrics.expenseRatioPct:.1f}%
Invoice Count: {report.keyMetrics.invoiceCount}
Avg Invoice Value: €{report.keyMetrics.avgInvoiceValue:,.2f}
Collection Rate: {collection}
Top Expense Categories: {top_categories}{reconciliation}

Write the summary now. After the summary, output a blank line, then a single line that begins exactly with "Sources: " and lists only the specific report inputs you drew from — for example the period's payroll register, bank confirmation, payslips, or named validation rules — separated by " · " (space, middle-dot, space). Do not cite an input or external standard that is not present above."""


def _reconciliation_context(report: FinancialReport) -> str:
    """
    Build a multi-stream reconciliation context block from the fused report.

    Feed the narrator values already present in the report, together with their
    limitations. Returns "" when no supporting streams are present.
    """
    lines: list[str] = []

    for ev in report.payrollEvents:
        if ev.employer_cost_total and ev.net_total:
            gap = ev.employer_cost_total - ev.net_total
            gap_pct = (gap / ev.net_total * 100) if ev.net_total else 0.0
            company = f" for {ev.company_name}" if ev.company_name else ""
            lines.append(
                f"\nPayroll document comparison ({ev.period}{company}):"
                f"\n  • Bank confirmation (employee net transfers): €{ev.net_total:,.2f}"
                f"\n  • Payroll register (reported total employer cost): €{ev.employer_cost_total:,.2f}"
                f"\n  • Register-reported employer cost is €{gap:,.2f} ({gap_pct:.0f}%) above bank-confirmed net wages."
                f"\n  This is a comparison of uploaded values, not verification that separate tax"
                f"\n  or social-insurance remittance transactions were paid. Employees covered: {ev.employee_count}."
                f"\n  Bank-confirmed: {'yes' if ev.bank_confirmed else 'no'}."
            )
            break

    if report.cashFlow:
        cf = report.cashFlow
        lines.append(
            f"\nDocument-based cash-flow view: operating €{cf.operating:,.2f}, "
            f"investing €{cf.investing:,.2f}, financing €{cf.financing:,.2f}, "
            f"net €{cf.net:,.2f}. Sales invoices are assumed collected and purchase/expense "
            f"invoices paid; generic bank-to-invoice matching is not implemented."
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


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, RateLimitError, APIConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
)
def _call_llm(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=450,
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()
