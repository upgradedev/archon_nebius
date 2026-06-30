"""
Unit tests for the PostgreSQL read models (backend/db/models.py).

Pure pydantic — no database. Verifies type coercion (UUID/date/datetime strings),
required vs optional fields, and that the models accept the shapes the schema
produces.
"""
from datetime import date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from db.models import (
    DocumentRecord, EmployeeRecord, EmployeePayrollRecord,
    PayrollEventRecord, ValidationResultRecord,
)

UID = "12345678-1234-5678-1234-567812345678"


def test_document_record_coerces_uuid_date_datetime():
    rec = DocumentRecord(
        id=UID, upload_id="u1", period="2026-01", source_file="x.pdf",
        doc_type="invoice", detected_lang="el", issue_date="2026-01-15",
        vendor_name="Acme", vendor_tax_id="EL1", recipient_name="Me",
        currency="EUR", total_amount=100.0, confidence=0.9,
        created_at="2026-01-15T10:00:00",
    )
    assert isinstance(rec.id, UUID)
    assert rec.issue_date == date(2026, 1, 15)
    assert isinstance(rec.created_at, datetime)
    assert rec.total_amount == 100.0


def test_document_record_allows_optional_nulls():
    rec = DocumentRecord(
        id=UID, upload_id="u1", period="2026-01", source_file="x.pdf",
        doc_type="unknown", detected_lang=None, issue_date=None,
        vendor_name=None, vendor_tax_id=None, recipient_name=None,
        currency="EUR", total_amount=0.0, confidence=None,
        created_at="2026-01-15T10:00:00",
    )
    assert rec.issue_date is None and rec.confidence is None


def test_document_record_missing_required_raises():
    with pytest.raises(ValidationError):
        DocumentRecord(id=UID, upload_id="u1")   # missing many required fields


def test_employee_record():
    rec = EmployeeRecord(id=UID, employee_code="E1", full_name="Maria",
                         tax_id="EL2", bank_account="GR16...", updated_at="2026-01-01T00:00:00")
    assert rec.employee_code == "E1"
    assert isinstance(rec.updated_at, datetime)


def test_employee_payroll_record_requires_net_pay():
    rec = EmployeePayrollRecord(
        id=UID, employee_id=UID, period="2026-01",
        gross_pay=1200.0, net_pay=950.0, employer_cost=1500.0,
        ika_employee=200.0, ika_employer=300.0, income_tax=50.0, document_id=UID,
    )
    assert rec.net_pay == 950.0
    assert isinstance(rec.employee_id, UUID)
    with pytest.raises(ValidationError):
        EmployeePayrollRecord(id=UID, employee_id=UID, period="2026-01")  # net_pay required


def test_payroll_event_record_optional_totals():
    rec = PayrollEventRecord(
        id=UID, period="2026-01", company_name="Acme",
        net_total=10000.0, gross_total=None, employer_cost_total=None,
        employee_count=None, is_complete=False, created_at="2026-01-31T12:00:00",
    )
    assert rec.is_complete is False
    assert rec.gross_total is None


def test_validation_result_record_source_files_list():
    rec = ValidationResultRecord(
        id=UID, period="2026-01", upload_id="u1",
        rule="R1: bank ≈ payslips", passed=True, severity="info",
        message="ok", source_files=["a.pdf", "b.pdf"], created_at="2026-01-31T12:00:00",
    )
    assert rec.source_files == ["a.pdf", "b.pdf"]
    assert rec.passed is True
