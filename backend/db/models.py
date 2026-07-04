"""
Pydantic models mirroring the PostgreSQL schema for use in FastAPI responses.

These are read models — writes go through direct SQL (psycopg2) to keep
the backend dependency footprint minimal. SQLAlchemy ORM is not used
intentionally: the query patterns here are simple and an ORM would add
complexity without benefit at this scale.
"""

from __future__ import annotations
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel


class DocumentRecord(BaseModel):
    id: UUID
    upload_id: str
    period: str
    source_file: str
    doc_type: str
    detected_lang: str | None = None
    issue_date: date | None = None
    vendor_name: str | None = None
    vendor_tax_id: str | None = None
    recipient_name: str | None = None
    currency: str
    total_amount: float
    confidence: float | None = None
    created_at: datetime


class EmployeeRecord(BaseModel):
    id: UUID
    employee_code: str | None = None
    full_name: str | None = None
    tax_id: str | None = None
    bank_account: str | None = None
    updated_at: datetime


class EmployeePayrollRecord(BaseModel):
    id: UUID
    employee_id: UUID
    period: str
    gross_pay: float | None = None
    net_pay: float
    employer_cost: float | None = None
    employee_social_security: float | None = None
    employer_social_security: float | None = None
    income_tax: float | None = None
    document_id: UUID | None = None


class PayrollEventRecord(BaseModel):
    id: UUID
    period: str
    company_name: str | None = None
    net_total: float | None = None
    gross_total: float | None = None
    employer_cost_total: float | None = None
    employee_count: int | None = None
    is_complete: bool
    created_at: datetime


class ValidationResultRecord(BaseModel):
    id: UUID
    period: str
    upload_id: str | None = None
    rule: str
    passed: bool
    severity: str
    message: str | None = None
    source_files: list[str]
    created_at: datetime
