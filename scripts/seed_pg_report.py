"""Seed a synthetic NEW-shape financial report into Object Storage.

Why this exists
---------------
The PostgreSQL read-model mirror (`backend/services/pg_sync.py`) only writes when
a report carries the relational sections `payrollEvents` / `employeeSummaries` /
`validationResults` — exactly what a real analysis Job emits
(`jobs/analysis/main.py`). Proving the mirror actually writes to the live,
IP-allowlisted PostgreSQL therefore needs such a report in Object Storage — but a
real analysis Job needs AI-Jobs compute quota, which may be 0.

This script breaks that dependency: it PUTs a valid new-shape report directly to
`reports/{period}/report.json`. A subsequent authenticated `GET /api/reports/{period}`
then triggers `materialize_report` on the backend Endpoint (the only in-VPC writer
that can reach the allowlisted cluster), so the PG write can be proven WITHOUT any
Job or quota. It is deliberately a SEED for a sentinel period (default 2099-12) so
it never clobbers a real reporting period.

The report shape mirrors `jobs/analysis/models/financial.py::FinancialReport`; only
the fields `pg_sync` reads are load-bearing, but a few descriptive top-level keys
are included so the seeded period renders like any other in the dashboard.
"""
from __future__ import annotations

import json
import os

# The three relational sections + the EXACT field names services/pg_sync.py reads.
# Keep these in sync with pg_sync.materialize_report if that reader changes.


def build_report(period: str) -> dict:
    """Return a {jobId, report, generatedAt} wrapper with populated relational
    sections. Pure + deterministic (no clock / no network) so it is unit-testable
    and reproducible."""
    report = {
        "period": period,
        "generatedAt": f"{period}-28T00:00:00+00:00",
        "executiveSummary": (
            "Seeded reference report used to exercise the PostgreSQL read-model "
            "mirror end-to-end. Two companies, four employees, four validations."
        ),
        # ── Relational sections the mirror writes (load-bearing field names) ──
        "payrollEvents": [
            {
                "company_name": "Aegean Trading Ltd",
                "net_total": 18250.00,
                "gross_total": 24100.00,
                "employer_cost_total": 31400.00,
                "employee_count": 3,
                "bank_confirmed": True,
            },
            {
                "company_name": "Ionian Services SA",
                "net_total": 9600.00,
                "gross_total": 12750.00,
                "employer_cost_total": 16520.00,
                "employee_count": 1,
                "bank_confirmed": False,
            },
        ],
        "employeeSummaries": [
            {"employee_code": "E001", "employee_name": "Maria Papadaki",
             "gross_pay": 9000.0, "net_pay": 6800.0, "employer_cost": 11700.0},
            {"employee_code": "E002", "employee_name": "Nikos Georgiou",
             "gross_pay": 8100.0, "net_pay": 6100.0, "employer_cost": 10530.0},
            {"employee_code": "E003", "employee_name": "Eleni Vasiliou",
             "gross_pay": 7000.0, "net_pay": 5350.0, "employer_cost": 9100.0},
            {"employee_code": "E004", "employee_name": "Dimitris Alexiou",
             "gross_pay": 12750.0, "net_pay": 9600.0, "employer_cost": 16520.0},
        ],
        "validationResults": [
            {"rule": "R1_bank_vs_payslips", "passed": True, "severity": "info",
             "message": "Bank transfer reconciles with payslip net totals (within 2%).",
             "source_files": ["bank_confirmation.pdf", "payslip_E001.pdf"]},
            {"rule": "R2_employer_contribution_ratio", "passed": True, "severity": "info",
             "message": "Employer contribution ratio within expected band.",
             "source_files": ["payroll_register.pdf"]},
            {"rule": "R3_payment_date", "passed": True, "severity": "info",
             "message": "Payment date present and consistent across documents.",
             "source_files": ["bank_confirmation.pdf"]},
            {"rule": "R4_employee_count", "passed": False, "severity": "warning",
             "message": "Register lists 4 employees; only 3 payslips were provided.",
             "source_files": ["payroll_register.pdf"]},
        ],
    }
    return {"jobId": f"seed-{period}", "report": report, "generatedAt": report["generatedAt"]}


def main() -> int:
    import boto3  # imported lazily so build_report stays dependency-free for tests

    period = os.environ.get("SEED_PERIOD", "2099-12").strip()
    bucket = os.environ["NEBIUS_BUCKET_NAME"]
    endpoint = os.environ["STORAGE_ENDPOINT_URL"]
    region = os.environ.get("NEBIUS_REGION", "eu-west1")
    key = f"reports/{period}/report.json"

    body = json.dumps(build_report(period)).encode()
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    print(f"seeded s3://{bucket}/{key} ({len(body)} bytes) for period {period}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
