"""
pnl_builder — the legacy report builder.

NOTE (finding): `pnl_builder.build_report()` is dead/legacy — it constructs a
FinancialReport WITHOUT the payrollEvents/employeeSummaries/validationResults/
vendorReconciliations fields that the model now requires, so it raises
ValidationError if called. The live endpoint (main.py) builds FinancialReport
inline and never calls build_report. These tests therefore cover only the pure,
still-correct helper functions it exposes.
"""
import pytest

from agents import pnl_builder
from models.financial import FinancialReport


def test_build_report_is_dead_code_raises(doc):
    # documents the breakage so a future fix is a deliberate, tested change
    with pytest.raises(Exception):
        pnl_builder.build_report("2026-01", [doc(doc_type="sales", total_amount=100)])


def test_expense_breakdown_categories(doc):
    docs = [
        doc(source_file="p.pdf", doc_type="payroll", total_amount=8_000),
        doc(source_file="u.pdf", doc_type="expense", total_amount=1_000, notes="electricity"),
        doc(source_file="s.pdf", doc_type="expense", total_amount=1_000, notes="cloud saas"),
        doc(source_file="m.pdf", doc_type="expense", total_amount=500, notes="marketing campaign"),
        doc(source_file="o.pdf", doc_type="expense", total_amount=300, notes="misc"),
    ]
    cats = {c.category: c for c in pnl_builder._build_expense_breakdown(docs)}
    assert cats["Payroll"].amount == 8_000.0
    assert "Utilities" in cats and "Software & Cloud" in cats
    assert "Marketing" in cats and "Operating Expenses" in cats
    # percentages sum to ~100
    assert round(sum(c.percentage for c in cats.values())) == 100


def test_vendor_summary_and_key_metrics(doc):
    docs = [
        doc(source_file="s1.pdf", doc_type="sales", total_amount=5_000),
        doc(source_file="e1.pdf", doc_type="expense", vendor_name="OTE", total_amount=1_000),
        doc(source_file="e2.pdf", doc_type="expense", vendor_name="OTE", total_amount=500),
    ]
    vendors = pnl_builder._build_vendor_summary(docs)
    assert vendors[0].name == "OTE" and vendors[0].invoiceCount == 2
    m = pnl_builder._build_key_metrics(docs, revenue=5_000, expenses=1_500)
    assert m.invoiceCount == 1
    assert m.avgInvoiceValue == 5_000.0
    assert m.expenseRatioPct == 30.0


def test_key_metrics_zero_revenue(doc):
    m = pnl_builder._build_key_metrics([doc(doc_type="expense", total_amount=100)],
                                       revenue=0, expenses=100)
    assert m.expenseRatioPct == 0.0
    assert m.avgInvoiceValue == 0.0
