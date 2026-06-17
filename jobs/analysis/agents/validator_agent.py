"""
ValidatorAgent (analysis tier) — analysis-time cross-document consistency checks.

Single responsibility: apply the same validation rules as the extraction-tier
validator, but operating on the analysis endpoint's ExtractedDoc model
(which comes from the aggregated documents.json in object storage).

This is intentionally a lightweight re-validation: the extraction job already
ran these rules and stored results.json. The analysis endpoint re-runs them as
a safety net in case documents from multiple upload batches are combined.

Rules:
  R1  bank.total ≈ sum(payslips) ±2%
  R2  employer_cost / net_pay in [1.25, 1.45]
  R3  bank.issue_date <= last day of period
  R4  register.employee_count == len(payslips)
"""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

from models.financial import ExtractedDoc, ValidationResult

log = logging.getLogger("archon.validator_agent")

PAYROLL_TYPES = {"payroll_register", "bank_confirmation", "payslip", "payroll"}


def run(period: str, docs: list[ExtractedDoc]) -> list[ValidationResult]:
    payroll_docs = [d for d in docs if d.doc_type in PAYROLL_TYPES]
    if not payroll_docs:
        return []

    bank = next((d for d in payroll_docs if d.doc_type == "bank_confirmation"), None)
    register = next((d for d in payroll_docs if d.doc_type == "payroll_register"), None)
    payslips = [d for d in payroll_docs if d.doc_type == "payslip"]

    results = [
        _r1(bank, payslips),
        _r2(register),
        _r3(bank, period),
        _r4(register, payslips),
    ]
    passed = sum(1 for r in results if r.passed)
    log.info("Validation for period %s: %d/%d passed", period, passed, len(results))
    return results


def _r1(bank: ExtractedDoc | None, payslips: list[ExtractedDoc]) -> ValidationResult:
    rule = "R1: bank.total ≈ sum(payslips) ±2%"
    if not bank or not payslips:
        return _skip(rule)
    slips_total = sum(s.total_amount for s in payslips)
    if slips_total == 0:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message="Payslip totals sum to zero.", source_files=[])
    ratio = abs(bank.total_amount - slips_total) / slips_total
    passed = ratio <= 0.02
    return ValidationResult(
        rule=rule, passed=passed,
        severity="error" if not passed else "info",
        message=f"Bank {bank.total_amount:.2f} vs payslips {slips_total:.2f} ({ratio*100:.1f}% deviation)",
        source_files=[bank.source_file] + [s.source_file for s in payslips],
    )


def _r2(register: ExtractedDoc | None) -> ValidationResult:
    rule = "R2: employer_cost / net_pay in [1.25, 1.45]"
    if not register or not register.employer_cost_total or not register.net_pay_total:
        return _skip(rule)
    if register.net_pay_total == 0:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message="Register net_pay_total is zero.", source_files=[])
    ratio = register.employer_cost_total / register.net_pay_total
    passed = 1.25 <= ratio <= 1.45
    return ValidationResult(
        rule=rule, passed=passed,
        severity="warning" if not passed else "info",
        message=f"employer_cost/net = {ratio:.3f} (expected 1.25–1.45)",
        source_files=[register.source_file],
    )


def _r3(bank: ExtractedDoc | None, period: str) -> ValidationResult:
    rule = "R3: bank.issue_date <= last day of period"
    if not bank or not bank.issue_date or not period or len(period) < 7:
        return _skip(rule)
    try:
        payment_date = date.fromisoformat(bank.issue_date)
        year, month = int(period[:4]), int(period[5:7])
        last_day = date(year, month, monthrange(year, month)[1])
        passed = payment_date <= last_day
        return ValidationResult(
            rule=rule, passed=passed,
            severity="warning" if not passed else "info",
            message=f"Payment {payment_date} vs period end {last_day}",
            source_files=[bank.source_file],
        )
    except (ValueError, IndexError) as exc:
        return ValidationResult(rule=rule, passed=False, severity="warning",
                                message=f"Date parse error: {exc}", source_files=[])


def _r4(register: ExtractedDoc | None, payslips: list[ExtractedDoc]) -> ValidationResult:
    rule = "R4: register.employee_count == len(payslips)"
    if not register or register.employee_count is None or not payslips:
        return _skip(rule)
    passed = register.employee_count == len(payslips)
    return ValidationResult(
        rule=rule, passed=passed,
        severity="warning" if not passed else "info",
        message=f"Register: {register.employee_count} employees, payslips found: {len(payslips)}",
        source_files=[register.source_file] + [s.source_file for s in payslips],
    )


def _skip(rule: str) -> ValidationResult:
    return ValidationResult(rule=rule, passed=True, severity="info",
                            message="Skipped — required documents absent.", source_files=[])
