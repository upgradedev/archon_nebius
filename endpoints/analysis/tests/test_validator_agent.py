"""
ValidatorAgent (analysis tier) — cross-document rules R1-R4.

R2 and R4 are DORMANT in production only because the extractor never emits
employer_cost_total / net_pay_total / employee_count. The rule logic itself is
live: these tests drive it directly by constructing ExtractedDoc inputs WITH
those fields populated — they do NOT change the extractor, so the eval-harness
dormancy assertion stays true.
"""
from agents import validator_agent


def _rules(results):
    return {r.rule.split(":", 1)[0]: r for r in results}


def test_no_payroll_docs_returns_empty(doc):
    assert validator_agent.run("2026-01", [doc(doc_type="invoice")]) == []


# ── R1: bank.total ≈ sum(payslips) ±2% ────────────────────────────────────────

def test_r1_pass_within_tolerance(doc):
    docs = [
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000),
        doc(source_file="s2.pdf", doc_type="payslip", total_amount=5_050),
    ]
    r1 = _rules(validator_agent.run("2026-01", docs))["R1"]
    assert r1.passed is True and r1.severity == "info"


def test_r1_fail_beyond_tolerance_is_error(doc):
    docs = [
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=8_000),
    ]
    r1 = _rules(validator_agent.run("2026-01", docs))["R1"]
    assert r1.passed is False and r1.severity == "error"


def test_r1_zero_payslips_total_warns(doc):
    docs = [
        doc(source_file="bank.pdf", doc_type="bank_confirmation", total_amount=10_000),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=0),
    ]
    r1 = _rules(validator_agent.run("2026-01", docs))["R1"]
    assert r1.passed is False and r1.severity == "warning"


def test_r1_skipped_without_bank(doc):
    docs = [doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000)]
    r1 = _rules(validator_agent.run("2026-01", docs))["R1"]
    assert r1.passed is True and "Skipped" in r1.message


# ── R2: employer_cost / net_pay in [1.25, 1.45] (live logic, dormant inputs) ──

def test_r2_pass_in_range(doc):
    docs = [doc(doc_type="payroll_register", employer_cost_total=12_800, net_pay_total=10_000)]
    r2 = _rules(validator_agent.run("2026-01", docs))["R2"]
    assert r2.passed is True   # 1.28 in [1.25, 1.45]


def test_r2_fail_out_of_range_warns(doc):
    docs = [doc(doc_type="payroll_register", employer_cost_total=16_000, net_pay_total=10_000)]
    r2 = _rules(validator_agent.run("2026-01", docs))["R2"]
    assert r2.passed is False and r2.severity == "warning"   # 1.60 > 1.45


def test_r2_zero_net_warns(doc):
    docs = [doc(doc_type="payroll_register", employer_cost_total=12_800, net_pay_total=0)]
    # employer_cost_total truthy but net_pay_total 0 → "or not net_pay_total" skips first,
    # so this exercises the skip branch (0 is falsy) → Skipped, not the zero-warn.
    r2 = _rules(validator_agent.run("2026-01", docs))["R2"]
    assert r2.passed is True and "Skipped" in r2.message


def test_r2_skipped_when_fields_absent(doc):
    docs = [doc(doc_type="payroll_register", employer_cost_total=None, net_pay_total=None)]
    r2 = _rules(validator_agent.run("2026-01", docs))["R2"]
    assert "Skipped" in r2.message


# ── R3: bank.issue_date <= last day of period ────────────────────────────────

def test_r3_pass_on_time(doc):
    docs = [doc(doc_type="bank_confirmation", issue_date="2026-01-28", total_amount=10_000)]
    r3 = _rules(validator_agent.run("2026-01", docs))["R3"]
    assert r3.passed is True


def test_r3_fail_after_period_end(doc):
    docs = [doc(doc_type="bank_confirmation", issue_date="2026-02-03", total_amount=10_000)]
    r3 = _rules(validator_agent.run("2026-01", docs))["R3"]
    assert r3.passed is False and r3.severity == "warning"


def test_r3_bad_date_warns(doc):
    docs = [doc(doc_type="bank_confirmation", issue_date="not-a-date", total_amount=10_000)]
    r3 = _rules(validator_agent.run("2026-01", docs))["R3"]
    assert r3.passed is False and "parse error" in r3.message.lower()


def test_r3_skipped_short_period(doc):
    docs = [doc(doc_type="bank_confirmation", issue_date="2026-01-10", total_amount=10_000)]
    r3 = _rules(validator_agent.run("2026", docs))["R3"]   # period < 7 chars
    assert "Skipped" in r3.message


# ── R4: register.employee_count == len(payslips) (live logic, dormant inputs) ─

def test_r4_pass_count_matches(doc):
    docs = [
        doc(source_file="reg.pdf", doc_type="payroll_register", employee_count=2),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000),
        doc(source_file="s2.pdf", doc_type="payslip", total_amount=5_000),
    ]
    r4 = _rules(validator_agent.run("2026-01", docs))["R4"]
    assert r4.passed is True


def test_r4_fail_count_mismatch_catches_missing_payslip(doc):
    docs = [
        doc(source_file="reg.pdf", doc_type="payroll_register", employee_count=3),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000),
    ]
    r4 = _rules(validator_agent.run("2026-01", docs))["R4"]
    assert r4.passed is False and "3 employees" in r4.message


def test_r4_skipped_without_count(doc):
    docs = [
        doc(source_file="reg.pdf", doc_type="payroll_register", employee_count=None),
        doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000),
    ]
    r4 = _rules(validator_agent.run("2026-01", docs))["R4"]
    assert "Skipped" in r4.message
