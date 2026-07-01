"""
Upload synthetic extracted documents to Nebius Object Storage for demo/testing.
Simulates what the extraction job would produce for the 7 sample PDFs in sample-data/generated/.

Usage:
    python scripts/upload_demo_docs.py

Requires: boto3, botocore (already in backend requirements)
Credentials are read from .env or environment variables.
"""
import json
import os
import boto3
from botocore.config import Config

BUCKET = os.getenv("NEBIUS_BUCKET_NAME", "archon-bucket")
ENDPOINT_URL = os.getenv("STORAGE_ENDPOINT_URL", os.getenv("NEBIUS_STORAGE_ENDPOINT_URL", "https://storage.eu-west1.nebius.cloud"))
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", os.getenv("NEBIUS_STORAGE_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", os.getenv("NEBIUS_STORAGE_SECRET_KEY", ""))

documents = [
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/attiki_odos_invoice_202601.pdf",
        "doc_type": "invoice",
        "detected_language": "el",
        "issue_date": "2026-01-31",
        "vendor_name": "ATTIKI ODOS AE",
        "vendor_tax_id": "094506571",
        "recipient_name": "REFLECTIVE IKE",
        "currency": "EUR",
        "original_currency": None,
        "original_amount": None,
        "subtotal": 68.87,
        "vat_amount": 16.53,
        "vat_rate_pct": 24.0,
        "vat_treatment": "standard",
        "total_amount": 85.40,
        "payment_due_date": "2026-02-14",
        "invoice_number": "ATTIKI-202601-0042",
        "notes": "Tolls January 2026 - Egnatia Odos",
        "confidence": 0.97,
        "employee_count": None, "gross_pay_total": None, "employer_cost_total": None,
        "net_pay_total": None, "employee_name": None, "employee_code": None,
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/anthropic_invoice_202601.pdf",
        "doc_type": "invoice",
        "detected_language": "en",
        "issue_date": "2026-01-31",
        "vendor_name": "Anthropic, PBC",
        "vendor_tax_id": None,
        "recipient_name": "Upgrade Fousekis E & Co",
        "currency": "EUR",
        "original_currency": "USD",
        "original_amount": 312.44,
        "subtotal": 300.07,
        "vat_amount": 0.0,
        "vat_rate_pct": 0.0,
        "vat_treatment": "reverse_charge",
        "total_amount": 300.07,
        "payment_due_date": "2026-02-14",
        "invoice_number": "INV-BF69A412-0042",
        "notes": "Claude API usage Jan 2026. Reverse charge Art 44.",
        "confidence": 0.96,
        "employee_count": None, "gross_pay_total": None, "employer_cost_total": None,
        "net_pay_total": None, "employee_name": None, "employee_code": None,
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/aws_invoice_202601.pdf",
        "doc_type": "invoice",
        "detected_language": "en",
        "issue_date": "2026-02-01",
        "vendor_name": "Amazon Web Services EMEA SARL",
        "vendor_tax_id": "LU26859887",
        "recipient_name": "Upgrade Fousekis E & Co",
        "currency": "EUR",
        "original_currency": "USD",
        "original_amount": 256.62,
        "subtotal": 246.48,
        "vat_amount": 0.0,
        "vat_rate_pct": 0.0,
        "vat_treatment": "reverse_charge",
        "total_amount": 246.48,
        "payment_due_date": None,
        "invoice_number": "EUINGR26-99001",
        "notes": "EC2 + S3 + RDS Jan 2026. B2B EU reverse charge.",
        "confidence": 0.95,
        "employee_count": None, "gross_pay_total": None, "employer_cost_total": None,
        "net_pay_total": None, "employee_name": None, "employee_code": None,
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/payroll_register_202601.pdf",
        "doc_type": "payroll_register",
        "detected_language": "el",
        "issue_date": "2026-01-31",
        "vendor_name": "REFLECTIVE IKE",
        "vendor_tax_id": "801234567",
        "recipient_name": None,
        "currency": "EUR",
        "original_currency": None,
        "original_amount": None,
        "subtotal": None,
        "vat_amount": None,
        "vat_rate_pct": None,
        "vat_treatment": None,
        "total_amount": 6930.00,
        "payment_due_date": "2026-01-31",
        "invoice_number": None,
        "notes": "Payroll register January 2026. 3 employees.",
        "confidence": 0.98,
        "employee_count": 3,
        "gross_pay_total": 5500.00,
        "employer_cost_total": 6930.00,
        "net_pay_total": 3994.74,
        "employee_name": None, "employee_code": None,
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/bank_confirmation_202601.pdf",
        "doc_type": "bank_confirmation",
        "detected_language": "el",
        "issue_date": "2026-01-31",
        "vendor_name": "TRAPEZA PEIRAIOS AE",
        "vendor_tax_id": None,
        "recipient_name": "REFLECTIVE IKE",
        "currency": "EUR",
        "original_currency": None,
        "original_amount": None,
        "subtotal": None,
        "vat_amount": None,
        "vat_rate_pct": None,
        "vat_treatment": None,
        "total_amount": 3994.74,
        "payment_due_date": None,
        "invoice_number": "TXN-20260131-44821",
        "notes": "Mass payroll transfer confirmation. Ref: PAYROLL-202601-REF",
        "confidence": 0.99,
        "employee_count": 3,
        "gross_pay_total": None, "employer_cost_total": None,
        "net_pay_total": 3994.74,
        "employee_name": None, "employee_code": None,
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/payslip_emp001_202601.pdf",
        "doc_type": "payslip",
        "detected_language": "el",
        "issue_date": "2026-01-31",
        "vendor_name": "REFLECTIVE IKE",
        "vendor_tax_id": "801234567",
        "recipient_name": "Papadopoulos Nikos",
        "currency": "EUR",
        "original_currency": None,
        "original_amount": None,
        "subtotal": None,
        "vat_amount": None,
        "vat_rate_pct": None,
        "vat_treatment": None,
        "total_amount": 1312.44,
        "payment_due_date": "2026-01-31",
        "invoice_number": None,
        "notes": "Payslip January 2026. Employee social security 16%, employer 26%.",
        "confidence": 0.98,
        "employee_count": None, "gross_pay_total": None,
        "employer_cost_total": 2268.00,
        "net_pay_total": 1312.44,
        "employee_name": "Papadopoulos Nikos",
        "employee_code": "EMP-001",
        "statement_balance": None, "statement_overdue": None, "statement_entries": None,
    },
    {
        "source_file": "raw-docs/2026-01/demo-upload-001/google_statement_202601.pdf",
        "doc_type": "account_statement",
        "detected_language": "en",
        "issue_date": "2026-01-31",
        "vendor_name": "GOOGLE CLOUD EMEA LIMITED",
        "vendor_tax_id": "IE6388047V",
        "recipient_name": "Upgrade Fousekis E & Co",
        "currency": "EUR",
        "original_currency": None,
        "original_amount": None,
        "subtotal": None,
        "vat_amount": None,
        "vat_rate_pct": None,
        "vat_treatment": None,
        "total_amount": 256.30,
        "payment_due_date": None,
        "invoice_number": None,
        "notes": "Statement Jan 2026. Outstanding: EUR 256.30. Overdue: EUR 0.",
        "confidence": 0.97,
        "employee_count": None, "gross_pay_total": None, "employer_cost_total": None,
        "net_pay_total": None, "employee_name": None, "employee_code": None,
        "statement_balance": 256.30,
        "statement_overdue": 0.0,
        "statement_entries": [
            {"document_number": "5537606065", "posting_date": "2025-12-01", "due_date": "2026-01-15",
             "original_amount": 198.44, "remaining_amount": 0.0, "is_overdue": False},
            {"document_number": "5561234001", "posting_date": "2026-01-01", "due_date": "2026-02-15",
             "original_amount": 211.30, "remaining_amount": 211.30, "is_overdue": False},
            {"document_number": "5561234002", "posting_date": "2026-01-15", "due_date": "2026-03-01",
             "original_amount": 45.00, "remaining_amount": 45.00, "is_overdue": False},
        ],
    },
]


def main():
    payload = {"documents": documents, "upload_id": "demo-upload-001", "period": "2026-01"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="eu-west1",
        config=Config(signature_version="s3v4"),
    )

    key = "extracted/2026-01/demo-upload-001/documents.json"
    s3.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")
    print(f"Uploaded {key} ({len(body)} bytes, {len(documents)} documents)")
    print(f"Call analysis: POST http://<endpoint>:8001/analyze -d '{{\"period\": \"2026-01\"}}'")


if __name__ == "__main__":
    main()
