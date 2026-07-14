"""
PnLAgent — the fusion-math core. Verifies that the P&L reports the TRUE
employer payroll cost (gross + employer social-security) from the register, not
the bank net, and that the three payroll subtypes are never double-counted.
"""
from agents import pnl_agent


# ── _compute_expenses / build_pnl: the employer-cost fusion (~72% gap over bank) ──────────────────────

def test_register_employer_cost_is_authoritative(doc):
    # bank net 10_000, but register says employer cost is 12_800 (gross + employer social-security).
    # The P&L expense MUST be the register's employer_cost_total, not the bank net.
    docs = [
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="reg.pdf", doc_type="payroll_register",
            total_amount=10_000, employer_cost_total=12_800, net_pay_total=10_000),
    ]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.expenses == 12_800.0


def test_payroll_not_double_counted_when_register_present(doc):
    # register + bank + 2 payslips for the SAME event → only the register's
    # employer_cost is counted; bank and payslips are skipped.
    docs = [
        doc(source_file="reg.pdf", doc_type="payroll_register",
            total_amount=10_000, employer_cost_total=12_800),
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000),
        doc(source_file="s2.pdf", doc_type="payslip", total_amount=5_000),
    ]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.expenses == 12_800.0


def test_register_falls_back_to_total_when_no_employer_cost(doc):
    docs = [doc(doc_type="payroll_register", total_amount=9_000, employer_cost_total=None)]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.expenses == 9_000.0


def test_bank_and_payslips_counted_when_no_register(doc):
    # No register → bank_confirmation stands in as the payroll cost (the naive floor).
    docs = [doc(doc_type="bank_confirmation", total_amount=10_000)]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.expenses == 10_000.0


def test_revenue_and_margins(doc):
    docs = [
        doc(source_file="sale.pdf", doc_type="sales", total_amount=20_000),
        doc(source_file="exp.pdf", doc_type="expense", total_amount=5_000),
    ]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.revenue == 20_000.0
    assert pnl.expenses == 5_000.0
    assert pnl.netProfit == 15_000.0
    assert pnl.grossMarginPct == 75.0
    assert pnl.operatingMarginPct == 75.0


def test_zero_revenue_margin_is_zero_not_div_error(doc):
    docs = [doc(doc_type="expense", total_amount=500)]
    pnl = pnl_agent.build_pnl("2026-01", docs)
    assert pnl.revenue == 0.0
    assert pnl.grossMarginPct == 0.0


# ── build_expense_breakdown ───────────────────────────────────────────────────

def test_expense_breakdown_categorises_and_percentages(doc):
    docs = [
        doc(source_file="p.pdf", doc_type="payroll_register",
            total_amount=8_000, employer_cost_total=8_000),
        doc(source_file="r.pdf", doc_type="expense", total_amount=2_000,
            notes="Μηνιαίο ενοίκιο γραφείου"),
    ]
    breakdown = {c.category: c for c in pnl_agent.build_expense_breakdown(docs)}
    assert breakdown["Payroll"].amount == 8_000.0
    assert breakdown["Rent & Facilities"].amount == 2_000.0
    assert breakdown["Payroll"].percentage == 80.0
    assert breakdown["Rent & Facilities"].percentage == 20.0


def test_expense_breakdown_uses_employer_cost_for_register(doc):
    docs = [doc(doc_type="payroll_register", total_amount=10_000, employer_cost_total=12_800)]
    cats = pnl_agent.build_expense_breakdown(docs)
    assert cats[0].category == "Payroll"
    assert cats[0].amount == 12_800.0


def test_expense_breakdown_empty_is_safe():
    assert pnl_agent.build_expense_breakdown([]) == []


def test_categorise_keyword_buckets(doc):
    cases = {
        "electricity bill ΔΕΗ": "Utilities",
        "AWS cloud subscription": "Software & Cloud",
        "Google Ads marketing": "Marketing",
        "office supplies": "Operating Expenses",
    }
    for note, expected in cases.items():
        cats = pnl_agent.build_expense_breakdown([doc(doc_type="expense", total_amount=100, notes=note)])
        assert cats[0].category == expected, note


# ── build_vendor_summary ──────────────────────────────────────────────────────

def test_vendor_summary_aggregates_and_counts(doc):
    docs = [
        doc(source_file="a.pdf", doc_type="expense", vendor_name="DEH", total_amount=300),
        doc(source_file="b.pdf", doc_type="expense", vendor_name="DEH", total_amount=200),
        doc(source_file="c.pdf", doc_type="invoice", vendor_name="OTE", total_amount=150),
    ]
    vendors = {v.name: v for v in pnl_agent.build_vendor_summary(docs)}
    assert vendors["DEH"].totalAmount == 500.0
    assert vendors["DEH"].invoiceCount == 2
    assert vendors["OTE"].invoiceCount == 1


def test_vendor_summary_skips_blank_vendor(doc):
    docs = [doc(doc_type="expense", vendor_name=None, total_amount=100)]
    assert pnl_agent.build_vendor_summary(docs) == []


def test_vendor_summary_top_10_only(doc):
    docs = [doc(source_file=f"{i}.pdf", doc_type="expense",
                vendor_name=f"V{i}", total_amount=i + 1) for i in range(15)]
    assert len(pnl_agent.build_vendor_summary(docs)) == 10


# ── build_key_metrics ─────────────────────────────────────────────────────────

def test_key_metrics_invoice_stats(doc):
    docs = [
        doc(source_file="s1.pdf", doc_type="sales", total_amount=1_000),
        doc(source_file="s2.pdf", doc_type="sales", total_amount=3_000),
        doc(source_file="e.pdf", doc_type="expense", total_amount=1_000),
    ]
    m = pnl_agent.build_key_metrics(docs, revenue=4_000, expenses=1_000)
    # "Invoices" counts EVERY invoice document (sales AND expense/purchase), not
    # only sales — an uploaded expense invoice must register.
    assert m.invoiceCount == 3
    assert m.avgInvoiceValue == round((1_000 + 3_000 + 1_000) / 3, 2)
    assert m.expenseRatioPct == 25.0
    assert m.cashBurnRate == round(1_000 / 30, 2)
    # Not derivable from a single period → None (rendered as N/A), never fabricated.
    assert m.revenueGrowthPct is None
    assert m.collectionRatePct is None


def test_key_metrics_no_revenue_no_div_error(doc):
    m = pnl_agent.build_key_metrics([], revenue=0, expenses=500)
    assert m.expenseRatioPct == 0.0
    assert m.avgInvoiceValue == 0.0
    assert m.invoiceCount == 0
