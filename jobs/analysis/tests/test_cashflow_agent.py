"""
CashFlowAgent — real cash movement uses the BANK transfer (net actually paid),
not the register's employer cost. This is the deliberate inverse of PnLAgent.
"""
from agents import cashflow_agent, pnl_agent


def test_operating_cashflow_uses_bank_net_not_employer_cost(doc):
    docs = [
        doc(source_file="sale.pdf", doc_type="sales", total_amount=20_000),
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        # register's employer cost (12_800) must NOT affect cash out
        doc(source_file="reg.pdf", doc_type="payroll_register",
            total_amount=10_000, employer_cost_total=12_800),
        doc(source_file="exp.pdf", doc_type="expense", total_amount=2_000),
    ]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    cf = cashflow_agent.build_cashflow("2026-01", docs, pnl)
    # 20_000 in - 10_000 bank payroll out - 2_000 expense out
    assert cf.operating == 8_000.0
    assert cf.net == 8_000.0
    assert cf.investing == 0.0
    assert cf.financing == 0.0
    assert cf.period == "2026-01"


def test_cashflow_invoice_counts_as_outflow(doc):
    docs = [doc(doc_type="invoice", total_amount=1_500)]
    cf = cashflow_agent.build_cashflow("2026-02", docs, pnl_agent.build_pnl("2026-02", docs))
    assert cf.operating == -1_500.0


def test_cashflow_empty(doc):
    cf = cashflow_agent.build_cashflow("2026-03", [], pnl_agent.build_pnl("2026-03", []))
    assert cf.operating == 0.0
    assert cf.net == 0.0
