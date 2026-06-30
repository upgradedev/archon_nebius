"""
EmployeeAgent — per-employee analytics and payroll-event summaries.
Gross/employer-cost are apportioned across payslips by each slip's net share.
"""
from agents import employee_agent


def test_no_payslips_returns_empty(doc):
    assert employee_agent.build_employee_summaries("2026-01", [doc(doc_type="invoice")]) == []


def test_summaries_without_register_have_net_only(doc):
    docs = [
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=1_200,
            employee_name="Maria", employee_code="E1"),
    ]
    out = employee_agent.build_employee_summaries("2026-01", docs)
    assert len(out) == 1
    assert out[0].net_pay == 1_200.0
    assert out[0].gross_pay is None and out[0].employer_cost is None
    assert out[0].employee_name == "Maria"


def test_summaries_apportion_gross_and_cost_by_net_share(doc):
    docs = [
        doc(source_file="reg.pdf", doc_type="payroll_register",
            gross_pay_total=12_000, employer_cost_total=15_000),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=3_000, employee_code="E1"),
        doc(source_file="s2.pdf", doc_type="payslip", total_amount=6_000, employee_code="E2"),
    ]
    out = {s.employee_code: s for s in employee_agent.build_employee_summaries("2026-01", docs)}
    # net total 9_000 → E1 share 1/3, E2 share 2/3
    assert out["E1"].gross_pay == 4_000.0
    assert out["E1"].employer_cost == 5_000.0
    assert out["E2"].gross_pay == 8_000.0
    assert out["E2"].employer_cost == 10_000.0


def test_summary_falls_back_to_vendor_name(doc):
    docs = [doc(doc_type="payslip", total_amount=900, employee_name=None, vendor_name="Nikos")]
    out = employee_agent.build_employee_summaries("2026-01", docs)
    assert out[0].employee_name == "Nikos"


# ── payroll event summaries ───────────────────────────────────────────────────

def test_event_summary_none_when_no_payroll(doc):
    assert employee_agent.build_payroll_event_summaries("2026-01", [doc(doc_type="invoice")], []) == []


def test_event_summary_uses_bank_net_total(doc):
    docs = [
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="reg.pdf", doc_type="payroll_register",
            recipient_name="My Co", gross_pay_total=12_000,
            employer_cost_total=15_000, employee_count=4),
    ]
    ev = employee_agent.build_payroll_event_summaries("2026-01", docs, [])[0]
    assert ev.net_total == 10_000.0
    assert ev.gross_total == 12_000.0
    assert ev.employer_cost_total == 15_000.0
    assert ev.employee_count == 4
    assert ev.bank_confirmed is True
    assert ev.company_name == "My Co"


def test_event_summary_counts_payslips_without_register_count(doc):
    docs = [
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=900),
        doc(source_file="s2.pdf", doc_type="payslip", total_amount=1_100),
    ]
    ev = employee_agent.build_payroll_event_summaries("2026-01", docs, [])[0]
    assert ev.net_total == 2_000.0
    assert ev.employee_count == 2
    assert ev.bank_confirmed is False


def test_event_summary_validation_passed_reflects_errors(doc):
    class _R:
        def __init__(self, passed, severity):
            self.passed, self.severity = passed, severity
    docs = [doc(doc_type="bank_confirmation", total_amount=10_000)]
    failing = [_R(False, "error")]
    passing = [_R(False, "warning"), _R(True, "error")]
    assert employee_agent.build_payroll_event_summaries("2026-01", docs, failing)[0].validation_passed is False
    assert employee_agent.build_payroll_event_summaries("2026-01", docs, passing)[0].validation_passed is True
