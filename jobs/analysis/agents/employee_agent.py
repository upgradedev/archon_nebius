"""
EmployeeAgent — per-employee payroll analytics.

Single responsibility: derive per-employee salary metrics from payslip
documents and enrich them with gross / employer cost from the payroll
register when the EventLinker has linked them.

Outputs:
  - list[EmployeeSummary]  — one record per employee per period
  - list[PayrollEventSummary] — one record per linked payroll event
"""

from __future__ import annotations

import logging
from collections import defaultdict

from models.financial import ExtractedDoc, EmployeeSummary, PayrollEventSummary

log = logging.getLogger("archon.employee_agent")

PAYROLL_TYPES = {"payroll_register", "bank_confirmation", "payslip", "payroll"}


def build_employee_summaries(
    period: str, docs: list[ExtractedDoc]
) -> list[EmployeeSummary]:
    payslips = [d for d in docs if d.doc_type == "payslip"]
    if not payslips:
        log.info("No payslip documents found for period %s", period)
        return []

    # Attempt to apportion gross/employer cost from the register proportionally
    register = next((d for d in docs if d.doc_type == "payroll_register"), None)
    net_total_from_slips = sum(s.total_amount for s in payslips) or 1.0

    summaries: list[EmployeeSummary] = []
    for slip in payslips:
        net = slip.total_amount
        gross: float | None = None
        cost: float | None = None

        if register:
            share = net / net_total_from_slips
            if register.gross_pay_total:
                gross = round(register.gross_pay_total * share, 2)
            if register.employer_cost_total:
                cost = round(register.employer_cost_total * share, 2)

        summaries.append(EmployeeSummary(
            employee_code=slip.employee_code,
            employee_name=slip.employee_name or slip.vendor_name,
            period=period,
            net_pay=round(net, 2),
            gross_pay=gross,
            employer_cost=cost,
        ))

    log.info("Built %d employee summaries for period %s", len(summaries), period)
    return summaries


def build_payroll_event_summaries(
    period: str, docs: list[ExtractedDoc], validation_results: list
) -> list[PayrollEventSummary]:
    """Build a high-level payroll event summary for the dashboard."""
    bank = next((d for d in docs if d.doc_type == "bank_confirmation"), None)
    register = next((d for d in docs if d.doc_type == "payroll_register"), None)
    payslips = [d for d in docs if d.doc_type == "payslip"]

    if not any([bank, register, payslips]):
        return []

    net_total = (
        bank.total_amount if bank
        else sum(s.total_amount for s in payslips)
    )
    employee_count = (
        register.employee_count if register and register.employee_count
        else len(payslips)
    )
    validation_passed = all(
        r.passed for r in validation_results if r.severity == "error"
    )

    return [PayrollEventSummary(
        period=period,
        company_name=register.recipient_name if register else None,
        net_total=round(net_total, 2),
        gross_total=round(register.gross_pay_total, 2) if register and register.gross_pay_total else None,
        employer_cost_total=round(register.employer_cost_total, 2) if register and register.employer_cost_total else None,
        employee_count=employee_count,
        bank_confirmed=bank is not None,
        validation_passed=validation_passed,
    )]
