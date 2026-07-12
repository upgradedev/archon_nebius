"""
Archon — Financial Analysis Job
Runs as a Nebius Serverless AI Job (on-demand CPU, terminates on completion).

One job per analysis request. Unique job name includes period + UUID so
concurrent users each get isolated compute and unique billing entries.

Pipeline (7 single-responsibility agents):
  1. ClassifierAgent         — re-classify doc_type for analysis context
  2. PnLAgent                — P&L (uses employer_cost from register, not bank net)
  3. CashFlowAgent           — cash flow (uses bank transfers for real cash)
  4. ValidatorAgent          — cross-document consistency checks
  5. EmployeeAgent           — per-employee salary analytics (payroll-event summaries
                               consume step 4's validation results)
  6. ReconciliationAgent     — vendor statement vs. invoice diff
  7. NarratorAgent           — LLM CFO-level executive summary (Nebius Inference API)

Reads from Nebius Object Storage:
  extracted/{period}/*/documents.json

Writes to Nebius Object Storage:
  reports/{period}/report.json

Environment variables (injected by backend via Nebius Job API):
  PERIOD                    - YYYY-MM
  JOB_ID                    - unique identifier (set by backend, defaults to UUID)
  NEBIUS_BUCKET_NAME
  STORAGE_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  NEBIUS_INFERENCE_BASE_URL, NEBIUS_INFERENCE_API_KEY
  ANALYSIS_MODEL            - default: meta-llama/Llama-3.3-70B-Instruct
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config

from agents.classifier import classify
from agents import (
    pnl_agent,
    cashflow_agent,
    employee_agent,
    validator_agent,
    reconciliation_agent,
)
from agents.narrator import build_summary
from models.financial import ExtractedDoc, FinancialReport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("archon.analysis-job")

BUCKET = os.environ["NEBIUS_BUCKET_NAME"]


_S3_CLIENT = None


def _s3():
    # Reuse one boto3 client across the many list/get/put calls per analysis run.
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url=os.getenv("STORAGE_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("NEBIUS_REGION", "eu-west1"),
            config=Config(signature_version="s3v4"),
        )
    return _S3_CLIENT


def _load_documents(period: str) -> list[ExtractedDoc]:
    prefix = f"extracted/{period}/"
    paginator = _s3().get_paginator("list_objects_v2")
    docs: list[ExtractedDoc] = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("documents.json"):
                body = _s3().get_object(Bucket=BUCKET, Key=key)["Body"].read()
                payload = json.loads(body)
                for d in payload.get("documents", []):
                    try:
                        docs.append(ExtractedDoc(**d))
                    except Exception as exc:
                        log.warning("Skipping malformed document: %s", exc)
    return docs


def _write_report(period: str, job_id: str, report: FinancialReport, generated_at: str) -> None:
    payload = {
        "jobId": job_id,
        "report": report.model_dump(),
        "generatedAt": generated_at,
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    _s3().put_object(
        Bucket=BUCKET,
        Key=f"reports/{period}/report.json",
        Body=body,
        ContentType="application/json",
    )
    log.info("Report written → reports/%s/report.json", period)


def main() -> None:
    period = os.environ["PERIOD"]
    job_id = os.getenv("JOB_ID", uuid.uuid4().hex[:8])
    log.info("=== Analysis job start — period=%s job_id=%s ===", period, job_id)

    all_docs = _load_documents(period)
    if not all_docs:
        raise RuntimeError(f"No extracted documents found for period {period}")
    log.info("Loaded %d documents", len(all_docs))

    # Step 1: classify
    all_docs = classify(all_docs)
    fin_docs = [d for d in all_docs if d.doc_type != "account_statement"]
    log.info("Financial docs: %d  |  Account statements: %d",
             len(fin_docs), len(all_docs) - len(fin_docs))

    # Step 2: P&L
    pnl = pnl_agent.build_pnl(period, fin_docs)
    expense_breakdown = pnl_agent.build_expense_breakdown(fin_docs)
    top_vendors = pnl_agent.build_vendor_summary(fin_docs)
    key_metrics = pnl_agent.build_key_metrics(fin_docs, pnl.revenue, pnl.expenses)

    # Step 3: cash flow
    cash_flow = cashflow_agent.build_cashflow(period, fin_docs, pnl)

    # Step 4: validation
    validation_results = validator_agent.run(period, fin_docs)

    # Step 5: employee analytics
    employee_summaries = employee_agent.build_employee_summaries(period, fin_docs)
    payroll_events = employee_agent.build_payroll_event_summaries(
        period, fin_docs, validation_results
    )

    # Step 6: reconciliation (all docs including statements)
    vendor_reconciliations = reconciliation_agent.run(period, all_docs)

    # Step 7: narrative
    report = FinancialReport(
        period=period,
        pnl=pnl,
        cashFlow=cash_flow,
        expenseBreakdown=expense_breakdown,
        topVendors=top_vendors,
        keyMetrics=key_metrics,
        payrollEvents=payroll_events,
        employeeSummaries=employee_summaries,
        validationResults=validation_results,
        vendorReconciliations=vendor_reconciliations,
        executiveSummary="",
    )
    report.executiveSummary = build_summary(report)

    generated_at = datetime.now(timezone.utc).isoformat()
    _write_report(period, job_id, report, generated_at)
    log.info("=== Analysis job complete — period=%s ===", period)


if __name__ == "__main__":
    main()
