"""
CashFlowAgent — derives cash flow statement from P&L and document metadata.

Single responsibility: produce a CashFlow model from available data.

Cash flow is estimated from P&L at this stage. When Nebius Managed PostgreSQL
is populated with historical data, this agent will switch to direct cash
movement tracking (bank confirmations → operating outflows, sales receipts →
operating inflows).
"""

from models.financial import ExtractedDoc, CashFlow, MonthlyPnL

PAYROLL_TYPES = {"payroll_register", "bank_confirmation", "payslip", "payroll"}


def build_cashflow(period: str, docs: list[ExtractedDoc], pnl: MonthlyPnL) -> CashFlow:
    """
    Derive operating, investing, and financing cash flows.

    Operating cash flow:
      - Use bank_confirmation.total_amount for payroll outflows (actual cash paid)
      - Use sales total_amount for inflows
      - Net = inflows - non-payroll expenses - bank payroll transfers

    Investing / Financing: zero until asset purchase or loan docs are present.
    """
    # Cash actually paid for payroll (bank transfer amount = real cash out)
    bank_payroll_out = sum(
        d.total_amount for d in docs if d.doc_type == "bank_confirmation"
    )
    # Non-payroll expense cash out
    non_payroll_out = sum(
        d.total_amount for d in docs
        if d.doc_type in ("invoice", "expense")
    )
    # Sales cash in (assume collected — refine with AR aging when available)
    sales_in = sum(d.total_amount for d in docs if d.doc_type == "sales")

    operating = round(sales_in - bank_payroll_out - non_payroll_out, 2)

    return CashFlow(
        period=period,
        operating=operating,
        investing=0.0,
        financing=0.0,
        net=operating,
    )
