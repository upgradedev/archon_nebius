"""
PayrollEvent — the unified view of one payroll cycle from three document types.

A single payroll event is represented by up to three documents:
  1. bank_confirmation  — bank batch transfer confirmation (net total paid)
  2. payroll_register   — official payroll sheet (gross + IKA + employer cost)
  3. payslips           — individual employee pay slips (net per person)

The EventLinkerAgent groups them; the ValidatorAgent cross-checks them.
"""

from __future__ import annotations
from pydantic import BaseModel
from models.document import ExtractedDocument


class PayrollEvent(BaseModel):
    period: str                                    # YYYY-MM
    company_name: str | None

    bank_confirmation: ExtractedDocument | None    # net total view
    payroll_register: ExtractedDocument | None     # employer cost view
    payslips: list[ExtractedDocument]              # per-employee view

    is_complete: bool                              # all three types present
