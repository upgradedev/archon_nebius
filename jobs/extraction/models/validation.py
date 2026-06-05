"""
ValidationResult — output of the ValidatorAgent.

One record per validation rule per payroll event.
Written to storage as validation/{period}/{upload_id}/results.json.
"""

from pydantic import BaseModel


class ValidationResult(BaseModel):
    rule: str                   # e.g. "R1: bank.total ≈ sum(payslips) ±2%"
    passed: bool
    severity: str               # "info" | "warning" | "error"
    message: str                # human-readable explanation
    source_files: list[str]     # documents involved in this check
