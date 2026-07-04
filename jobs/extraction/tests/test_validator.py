"""
Extraction ValidatorAgent — R1-R4 over PayrollEvent objects.

R2/R4 logic is live; it is dormant in production only because the extractor
doesn't emit employer_cost_total/net_pay_total/employee_count. These tests drive
the logic by building events with those fields set — without touching the
extractor — so the eval dormancy assertion remains valid.
"""
from agents import validator
from models.document import DocType
from models.event import PayrollEvent


def _event(bank=None, register=None, payslips=None, period="2026-01", company="Acme"):
    return PayrollEvent(
        period=period, company_name=company,
        bank_confirmation=bank, payroll_register=register,
        payslips=payslips or [], is_complete=False,
    )


def _by_rule(results):
    return {r.rule.split(":", 1)[0]: r for r in results}


# ── R1 ────────────────────────────────────────────────────────────────────────

def test_r1_pass(doc):
    ev = _event(
        bank=doc(doc_type=DocType.BANK_CONFIRMATION, total_amount=10_000),
        payslips=[doc(source_file="s1.pdf", doc_type=DocType.PAYSLIP, total_amount=5_000),
                  doc(source_file="s2.pdf", doc_type=DocType.PAYSLIP, total_amount=5_050)],
    )
    assert _by_rule(validator.run([ev]))["R1"].passed is True


def test_r1_fail_error_severity(doc):
    ev = _event(
        bank=doc(doc_type=DocType.BANK_CONFIRMATION, total_amount=10_000),
        payslips=[doc(doc_type=DocType.PAYSLIP, total_amount=7_000)],
    )
    r1 = _by_rule(validator.run([ev]))["R1"]
    assert r1.passed is False and r1.severity == "error"


def test_r1_zero_payslips_warns(doc):
    ev = _event(
        bank=doc(doc_type=DocType.BANK_CONFIRMATION, total_amount=10_000),
        payslips=[doc(doc_type=DocType.PAYSLIP, total_amount=0)],
    )
    r1 = _by_rule(validator.run([ev]))["R1"]
    assert r1.passed is False and r1.severity == "warning"


def test_r1_skip_incomplete(doc):
    ev = _event(payslips=[doc(doc_type=DocType.PAYSLIP, total_amount=5_000)])
    assert "Skipped" in _by_rule(validator.run([ev]))["R1"].message


# ── R2 ────────────────────────────────────────────────────────────────────────

def test_r2_pass(doc):
    ev = _event(register=doc(doc_type=DocType.PAYROLL_REGISTER,
                             employer_cost_total=12_800, net_pay_total=10_000))
    assert _by_rule(validator.run([ev]))["R2"].passed is True


def test_r2_fail_warns(doc):
    ev = _event(register=doc(doc_type=DocType.PAYROLL_REGISTER,
                             employer_cost_total=20_000, net_pay_total=10_000))
    r2 = _by_rule(validator.run([ev]))["R2"]
    assert r2.passed is False and r2.severity == "warning"


def test_r2_skip_when_fields_absent(doc):
    ev = _event(register=doc(doc_type=DocType.PAYROLL_REGISTER))
    assert "Skipped" in _by_rule(validator.run([ev]))["R2"].message


def test_r2_zero_net_is_skipped_not_warned(doc):
    # net_pay_total == 0 is caught by the leading falsy guard, so R2 is SKIPPED
    # (ratio undefined without a positive net). The old "net is zero" warning
    # branch was unreachable dead code and was removed; pin the contract here.
    ev = _event(register=doc(doc_type=DocType.PAYROLL_REGISTER,
                             employer_cost_total=12_800, net_pay_total=0))
    r2 = _by_rule(validator.run([ev]))["R2"]
    assert r2.passed is True
    assert r2.severity == "info"
    assert "Skipped" in r2.message
    assert "zero" not in r2.message.lower()


# ── R3 ────────────────────────────────────────────────────────────────────────

def test_r3_pass(doc):
    ev = _event(bank=doc(doc_type=DocType.BANK_CONFIRMATION, issue_date="2026-01-28"))
    assert _by_rule(validator.run([ev]))["R3"].passed is True


def test_r3_fail_after_month_end(doc):
    ev = _event(bank=doc(doc_type=DocType.BANK_CONFIRMATION, issue_date="2026-02-05"))
    assert _by_rule(validator.run([ev]))["R3"].passed is False


def test_r3_bad_date(doc):
    ev = _event(bank=doc(doc_type=DocType.BANK_CONFIRMATION, issue_date="13/13/2026"))
    r3 = _by_rule(validator.run([ev]))["R3"]
    assert r3.passed is False and "parse error" in r3.message.lower()


def test_r3_skip_unknown_period(doc):
    ev = _event(bank=doc(doc_type=DocType.BANK_CONFIRMATION, issue_date="2026-01-10"),
                period="unknown")
    assert "Skipped" in _by_rule(validator.run([ev]))["R3"].message


# ── R4 ────────────────────────────────────────────────────────────────────────

def test_r4_pass(doc):
    ev = _event(
        register=doc(doc_type=DocType.PAYROLL_REGISTER, employee_count=2),
        payslips=[doc(source_file="s1.pdf", doc_type=DocType.PAYSLIP, total_amount=1),
                  doc(source_file="s2.pdf", doc_type=DocType.PAYSLIP, total_amount=1)],
    )
    assert _by_rule(validator.run([ev]))["R4"].passed is True


def test_r4_fail(doc):
    ev = _event(
        register=doc(doc_type=DocType.PAYROLL_REGISTER, employee_count=5),
        payslips=[doc(doc_type=DocType.PAYSLIP, total_amount=1)],
    )
    assert _by_rule(validator.run([ev]))["R4"].passed is False


def test_r4_skip_without_count(doc):
    ev = _event(register=doc(doc_type=DocType.PAYROLL_REGISTER, employee_count=None),
                payslips=[doc(doc_type=DocType.PAYSLIP, total_amount=1)])
    assert "Skipped" in _by_rule(validator.run([ev]))["R4"].message


def test_sources_collects_all_files(doc):
    ev = _event(
        bank=doc(source_file="bank.pdf", doc_type=DocType.BANK_CONFIRMATION, total_amount=10_000),
        register=doc(source_file="reg.pdf", doc_type=DocType.PAYROLL_REGISTER),
        payslips=[doc(source_file="s1.pdf", doc_type=DocType.PAYSLIP, total_amount=10_000)],
    )
    r1 = _by_rule(validator.run([ev]))["R1"]
    assert set(r1.source_files) >= {"bank.pdf", "s1.pdf"}
