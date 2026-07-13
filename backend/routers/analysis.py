import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from services import nebius, pg_sync, storage

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class AnalyzeRequest(BaseModel):
    period: str = Field(..., pattern=_PERIOD_PATTERN)


@router.post("/analyze")
def trigger_analysis(req: AnalyzeRequest):
    """Submit an on-demand analysis job and return its ID for polling."""
    try:
        return nebius.submit_analysis_job(req.period)
    except nebius.ComputeCapacityUnavailable as exc:
        # Every compute preset failed to provision — actionable 503, not a 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analysis job submission failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit analysis job: {type(exc).__name__}",
        ) from exc


@router.get("/analyze/{job_id}")
def get_analysis_job(job_id: str):
    """Poll the status of a running analysis job."""
    try:
        return nebius.get_job_status(job_id)
    except Exception as exc:
        logger.exception("Analysis job status fetch failed for %s", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {type(exc).__name__}",
        ) from exc


@router.get("/reports/{period}")
def get_report(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Fetch a completed financial report for a period (reads from Object Storage).

    Object Storage is the source of truth. On a successful read we also mirror
    the report's relational data into PostgreSQL (best-effort — never blocks or
    fails the response), keeping the read-model tables in sync with the report
    served here.
    """
    try:
        report = storage.download_json(f"reports/{period}/report.json")
        # Best-effort relational mirror. Isolated so a DB hiccup can never turn a
        # good report read into an error.
        try:
            pg_sync.materialize_report(period, report)
        except Exception:
            logger.warning("PG materialization raised for %s — ignoring", period, exc_info=True)
        return report
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail=f"Report not found for period {period}") from exc
        logger.exception("Storage error fetching report for %s", period)
        raise HTTPException(status_code=502, detail="Storage error retrieving report") from exc
    except Exception as exc:
        logger.exception("Report fetch failed for %s", period)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch report: {type(exc).__name__}",
        ) from exc
