from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from services import nebius, storage

router = APIRouter()

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class AnalyzeRequest(BaseModel):
    period: str = Field(..., pattern=_PERIOD_PATTERN)


@router.post("/analyze")
def trigger_analysis(req: AnalyzeRequest):
    """Submit an on-demand analysis job and return its ID for polling."""
    try:
        return nebius.submit_analysis_job(req.period)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to submit analysis job: {exc}") from exc


@router.get("/analyze/{job_id}")
def get_analysis_job(job_id: str):
    """Poll the status of a running analysis job."""
    try:
        return nebius.get_job_status(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {exc}") from exc


@router.get("/reports/{period}")
def get_report(period: str = Path(..., pattern=_PERIOD_PATTERN)):
    """Fetch a completed financial report for a period (reads from Object Storage)."""
    try:
        return storage.download_json(f"reports/{period}/report.json")
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail=f"Report not found for period {period}") from exc
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch report: {exc}") from exc
