"""
CashFlowAgent — derives a provisional document-based cash-flow view.

Single responsibility: produce a CashFlow model from the classified documents.

bank_confirmation.total_amount is treated as the observed payroll cash out (the
net transfer), while the P&L reads the register-reported employer cost. Until
general payment and collection linking is implemented, sales invoices are
assumed collected and purchase/expense documents are assumed paid. Investing /
financing stay zero until asset-purchase or loan documents are supported.
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
    # Assumption-based non-payroll outflow until payment linking is implemented.
    non_payroll_out = sum(
        d.total_amount for d in docs
        if d.doc_type in ("invoice", "expense")
    )
    # Assumption-based sales inflow until collection linking is implemented.
    sales_in = sum(d.total_amount for d in docs if d.doc_type == "sales")

    operating = round(sales_in - bank_payroll_out - non_payroll_out, 2)

    return CashFlow(
        period=period,
        operating=operating,
        investing=0.0,
        financing=0.0,
        net=operating,
    )
