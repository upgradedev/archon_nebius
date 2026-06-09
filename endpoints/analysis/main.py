"""
Archon — Financial Analysis Endpoint
Runs as a Nebius Serverless AI Endpoint (always-on).

Pipeline (single-responsibility agents in sequence):
  1. ClassifierAgent       — re-classify doc_type for analysis context
  2. PnLAgent              — P&L aggregation (uses employer_cost from register, not bank net)
  3. CashFlowAgent         — cash flow derivation (uses bank transfers for real cash movements)
  4. EmployeeAgent         — per-employee salary analytics from payslip + register
  5. ValidatorAgent        — cross-document consistency re-validation
  6. ReconciliationAgent   — vendor statement vs. uploaded invoices diff
  7. NarratorAgent         — LLM-written CFO-level executive summary

account_statement docs are excluded from P&L/cash flow; used only by ReconciliationAgent.

Reads from Nebius Object Storage:
  extracted/{period}/*/documents.json

Writes to:
  reports/{period}/report.json
"""

import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from agents.classifier import classify
from agents import pnl_agent, cashflow_agent, employee_agent, validator_agent, reconciliation_agent
from agents.narrator import build_summary
from models.financial import ExtractedDoc, FinancialReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("archon.analysis")


class Settings(BaseSettings):
    nebius_bucket_name: str = "archon-docs"
    storage_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    nebius_region: str = "eu-north1"
    database_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()


def _apply_schema() -> None:
    """Apply backend/db/schema.sql if DATABASE_URL is set and schema not yet applied."""
    if not settings.database_url:
        log.info("DATABASE_URL not set — skipping schema migration")
        return
    try:
        import psycopg2
        schema_path = pathlib.Path(__file__).parent.parent.parent / "backend" / "db" / "schema.sql"
        if not schema_path.exists():
            # Fallback: schema is bundled next to this file in the container
            schema_path = pathlib.Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            log.warning("schema.sql not found — skipping migration")
            return
        sql = schema_path.read_text()
        conn = psycopg2.connect(settings.database_url, connect_timeout=10)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.close()
        log.info("Schema migration applied successfully")
    except Exception as exc:
        log.warning("Schema migration failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_schema()
    yield


app = FastAPI(title="Archon Analysis Endpoint", version="2.1.0", lifespan=lifespan)


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url or None,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.nebius_region,
        config=Config(signature_version="s3v4"),
    )


def _load_documents(period: str) -> list[ExtractedDoc]:
    prefix = f"extracted/{period}/"
    paginator = _s3().get_paginator("list_objects_v2")
    docs: list[ExtractedDoc] = []
    for page in paginator.paginate(Bucket=settings.nebius_bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("documents.json"):
                body = _s3().get_object(Bucket=settings.nebius_bucket_name, Key=key)["Body"].read()
                payload = json.loads(body)
                for d in payload.get("documents", []):
                    try:
                        docs.append(ExtractedDoc(**d))
                    except Exception as exc:
                        log.warning("Skipping malformed document: %s", exc)
    return docs


class AnalyzeRequest(BaseModel):
    period: str   # YYYY-MM


class AnalyzeResponse(BaseModel):
    jobId: str
    report: FinancialReport
    generatedAt: str


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    log.info("=== Analysis start — period=%s ===", req.period)

    all_docs = _load_documents(req.period)
    if not all_docs:
        raise HTTPException(status_code=404, detail=f"No extracted documents for period {req.period}")
    log.info("Loaded %d documents", len(all_docs))

    # Step 1: classify
    all_docs = classify(all_docs)

    # Separate financial docs from statements (statements excluded from P&L/cash flow)
    fin_docs = [d for d in all_docs if d.doc_type != "account_statement"]
    log.info("Financial docs: %d, Account statements: %d",
             len(fin_docs), len(all_docs) - len(fin_docs))

    # Step 2: P&L (financial docs only)
    pnl = pnl_agent.build_pnl(req.period, fin_docs)
    expense_breakdown = pnl_agent.build_expense_breakdown(fin_docs)
    top_vendors = pnl_agent.build_vendor_summary(fin_docs)
    key_metrics = pnl_agent.build_key_metrics(fin_docs, pnl.revenue, pnl.expenses)

    # Step 3: cash flow (financial docs only)
    cash_flow = cashflow_agent.build_cashflow(req.period, fin_docs, pnl)

    # Step 4: validation
    validation_results = validator_agent.run(req.period, fin_docs)

    # Step 5: employee analytics
    employee_summaries = employee_agent.build_employee_summaries(req.period, fin_docs)
    payroll_events = employee_agent.build_payroll_event_summaries(req.period, fin_docs, validation_results)

    # Step 6: reconciliation (uses ALL docs including statements)
    vendor_reconciliations = reconciliation_agent.run(req.period, all_docs)

    # Step 7: narrative (full picture including reconciliation gaps)
    report = FinancialReport(
        period=req.period,
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
    _cache_report(req.period, report, generated_at)

    log.info("=== Analysis complete — period=%s ===", req.period)
    return AnalyzeResponse(jobId="n/a", report=report, generatedAt=generated_at)


@app.get("/reports/{period}", response_model=AnalyzeResponse)
def get_report(period: str):
    key = f"reports/{period}/report.json"
    try:
        body = _s3().get_object(Bucket=settings.nebius_bucket_name, Key=key)["Body"].read()
        return json.loads(body)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No report for period {period}") from exc


@app.get("/health")
def health():
    return {"status": "ok", "service": "archon-analysis", "version": "2.1.0"}


def _cache_report(period: str, report: FinancialReport, generated_at: str) -> None:
    payload = {"jobId": "n/a", "report": report.model_dump(), "generatedAt": generated_at}
    body = json.dumps(payload, ensure_ascii=False).encode()
    _s3().put_object(
        Bucket=settings.nebius_bucket_name,
        Key=f"reports/{period}/report.json",
        Body=body,
        ContentType="application/json",
    )
