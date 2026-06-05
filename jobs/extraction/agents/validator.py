"""
ValidatorAgent — cross-document consistency checks for payroll events.

Single responsibility: apply deterministic validation rules across the three
document subtypes that make up a payroll event. Produces a ValidationResult
per rule per event. Results are written to storage alongside extracted docs.

Rules enforced:
  R1  bank.total_amount ≈ sum(payslips.total_amount)  within 2 %
  R2  register.employer_cost_total / register.net_pay_total in [1.25, 1.45]
        (IKA employer share is 25-35 % of gross; typical range is 125-145 % of net)
  R3  bank.issue_date <= last calendar day of the stated period
  R4  register.employee_count == len(payslips)  (when both present)
"""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

from models.event import PayrollEvent
from models.validation import ValidationResult

log = logging.getLogger("archon.validator")


def run(events: list[PayrollEvent]) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for event in events:
        results.extend(_validate_event(event))
    return results


# ── per-event validation ──────────────────────────────────────────────────────

def _validate_event(event: PayrollEvent) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    ref = f"{event.period}/{event.company_name or 'unknown'}"

    results.append(_r1_bank_vs_payslips(event, ref))
    results.append(_r2_employer_cost_ratio(event, ref))
    results.append(_r3_payment_date(event, ref))
    results.append(_r4_employee_count(event, ref))

    passed = sum(1 for r in results if r.passed)
    log.info("Validation %s: %d/%d rules passed", ref, passed, len(results))
    return results


def _r1_bank_vs_payslips(event: PayrollEvent, ref: str) -> ValidationResult:
    rule = "R1: bank.total ≈ sum(payslips) ±2%"
    if event.bank_confirmation is None or not event.payslips:
        return ValidationResult(rule=rule, passed=True, severity="info",
                                message="Skipped — incomplete event (missing bank or payslips).",
                                source_files=_sources(event))
    bank_total = event.bank_confirmation.total_amount
    slips_total = sum(s.total_amount for s in event.payslips)
    if slips_total == 0:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message="Payslip totals sum to zero.",
                                source_files=_sources(event))
    ratio = abs(bank_total - slips_total) / slips_total
    passed = ratio <= 0.02
    return ValidationResult(
        rule=rule, passed=passed,
        severity="error" if not passed else "info",
        message=(
            f"Bank {bank_total:.2f} vs payslips {slips_total:.2f} "
            f"({ratio * 100:.1f}% deviation — threshold 2%)"
        ),
        source_files=_sources(event),
    )


def _r2_employer_cost_ratio(event: PayrollEvent, ref: str) -> ValidationResult:
    rule = "R2: employer_cost / net_pay in [1.25, 1.45]"
    reg = event.payroll_register
    if reg is None or not reg.employer_cost_total or not reg.net_pay_total:
        return ValidationResult(rule=rule, passed=True, severity="info",
                                message="Skipped — payroll register or cost fields absent.",
                                source_files=_sources(event))
    if reg.net_pay_total == 0:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message="Register net_pay_total is zero.",
                                source_files=_sources(event))
    ratio = reg.employer_cost_total / reg.net_pay_total
    passed = 1.25 <= ratio <= 1.45
    return ValidationResult(
        rule=rule, passed=passed,
        severity="warning" if not passed else "info",
        message=(
            f"employer_cost {reg.employer_cost_total:.2f} / net {reg.net_pay_total:.2f} "
            f"= {ratio:.3f} (expected 1.25–1.45)"
        ),
        source_files=_sources(event),
    )


def _r3_payment_date(event: PayrollEvent, ref: str) -> ValidationResult:
    rule = "R3: bank.issue_date <= last day of period"
    bank = event.bank_confirmation
    if bank is None or not bank.issue_date or event.period == "unknown":
        return ValidationResult(rule=rule, passed=True, severity="info",
                                message="Skipped — bank confirmation or period absent.",
                                source_files=_sources(event))
    try:
        payment_date = date.fromisoformat(bank.issue_date)
        year, month = int(event.period[:4]), int(event.period[5:7])
        last_day = date(year, month, monthrange(year, month)[1])
        passed = payment_date <= last_day
        return ValidationResult(
            rule=rule, passed=passed,
            severity="warning" if not passed else "info",
            message=f"Payment date {payment_date} vs period end {last_day}",
            source_files=_sources(event),
        )
    except (ValueError, IndexError) as exc:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message=f"Date parse error: {exc}",
                                source_files=_sources(event))


def _r4_employee_count(event: PayrollEvent, ref: str) -> ValidationResult:
    rule = "R4: register.employee_count == len(payslips)"
    reg = event.payroll_register
    if reg is None or reg.employee_count is None or not event.payslips:
        return ValidationResult(rule=rule, passed=True, severity="info",
                                message="Skipped — register or payslips absent.",
                                source_files=_sources(event))
    passed = reg.employee_count == len(event.payslips)
    return ValidationResult(
        rule=rule, passed=passed,
        severity="warning" if not passed else "info",
        message=(
            f"Register reports {reg.employee_count} employees, "
            f"found {len(event.payslips)} payslips"
        ),
        source_files=_sources(event),
    )


def _sources(event: PayrollEvent) -> list[str]:
    files = []
    if event.bank_confirmation:
        files.append(event.bank_confirmation.source_file)
    if event.payroll_register:
        files.append(event.payroll_register.source_file)
    files.extend(s.source_file for s in event.payslips)
    return files
