"""
Executive narrator — uses LLM to write a concise English executive summary
from the computed financial metrics.
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

    prompt = f"""You are a CFO-level financial analyst. Write a concise executive summary (3-4 sentences, plain English, no bullet points) for the following monthly financial data.

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
Top Expense Categories: {', '.join(e.category for e in report.expenseBreakdown[:3])}

Write the summary now:"""

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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _call_llm(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()
