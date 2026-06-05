"""
Archon — Financial Analysis Endpoint
Runs as a Nebius Serverless AI Endpoint (always-on).

Reads extracted document JSONs from object storage,
runs the agentic financial pipeline, and returns a FinancialReport.
"""

import os
import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from agents.classifier import classify
from agents.pnl_builder import build_report
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

    class Config:
        env_file = ".env"


settings = Settings()
app = FastAPI(title="Archon Analysis Endpoint", version="1.0.0")


def s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url or None,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.nebius_region,
        config=Config(signature_version="s3v4"),
    )


def load_documents(period: str) -> list[ExtractedDoc]:
    prefix = f"extracted/{period}/"
    paginator = s3().get_paginator("list_objects_v2")
    docs: list[ExtractedDoc] = []
    for page in paginator.paginate(Bucket=settings.nebius_bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("documents.json"):
                body = s3().get_object(Bucket=settings.nebius_bucket_name, Key=key)["Body"].read()
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
    log.info("Analyzing period %s", req.period)

    docs = load_documents(req.period)
    if not docs:
        raise HTTPException(status_code=404, detail=f"No extracted documents found for period {req.period}")

    log.info("Loaded %d documents", len(docs))

    classified = classify(docs)
    report = build_report(req.period, classified)
    report.executiveSummary = build_summary(report)

    generated_at = datetime.now(timezone.utc).isoformat()

    # Cache report to storage for fast retrieval
    _cache_report(req.period, report, generated_at)

    return AnalyzeResponse(jobId="n/a", report=report, generatedAt=generated_at)


@app.get("/reports/{period}", response_model=AnalyzeResponse)
def get_report(period: str):
    key = f"reports/{period}/report.json"
    try:
        body = s3().get_object(Bucket=settings.nebius_bucket_name, Key=key)["Body"].read()
        return json.loads(body)
    except s3().exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"No report cached for period {period}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok", "service": "archon-analysis"}


def _cache_report(period: str, report: FinancialReport, generated_at: str) -> None:
    payload = {"jobId": "n/a", "report": report.model_dump(), "generatedAt": generated_at}
    body = json.dumps(payload, ensure_ascii=False).encode()
    s3().put_object(
        Bucket=settings.nebius_bucket_name,
        Key=f"reports/{period}/report.json",
        Body=body,
        ContentType="application/json",
    )
