import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import verify_firebase_token
from services import job_audit, nebius

logger = logging.getLogger(__name__)
router = APIRouter()

# Our own accounts, excluded from the "third-party live-test" view so what remains
# is external (e.g. judge) activity. Override via JOB_AUDIT_KNOWN_IDENTITIES (comma
# separated uids/emails).
import os

_KNOWN_IDENTITIES = [
    e.strip() for e in os.getenv(
        "JOB_AUDIT_KNOWN_IDENTITIES",
        "ci@archon.local,e2e-test@archon-pnl.web.app,judge@archon-pnl.web.app",
    ).split(",") if e.strip()
]

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class JobRequest(BaseModel):
    uploadId: str
    period: str = Field(..., pattern=_PERIOD_PATTERN)


class JobResponse(BaseModel):
    id: str
    status: str
    period: str
    documentsCount: int
    createdAt: str
    completedAt: str | None = None
    errorMessage: str | None = None
    progress: int | None = None


@router.post("/jobs", response_model=JobResponse)
def submit_job(req: JobRequest, identity: dict = Depends(verify_firebase_token)):
    try:
        job = nebius.submit_extraction_job(req.uploadId, req.period)
        # Best-effort audit trail — never blocks the submission.
        job_audit.record_job_run(job, "extraction", identity)
        return JobResponse(**job)
    except nebius.ComputeCapacityUnavailable as exc:
        # Every compute preset failed to provision — surface an actionable 503
        # instead of a generic 500 or a silent stall.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Extraction job submission failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit extraction job: {type(exc).__name__}",
        ) from exc


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    try:
        job = nebius.get_job_status(job_id)
        return JobResponse(
            id=job["id"],
            status=job["status"],
            period="",
            documentsCount=0,
            createdAt="",
            completedAt=job.get("completedAt"),
            errorMessage=job.get("errorMessage"),
            progress=job.get("progress"),
        )
    except Exception as exc:
        logger.exception("Job status fetch failed for %s", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {type(exc).__name__}",
        ) from exc


@router.get("/job-runs")
def list_job_runs(
    limit: int = Query(100, ge=1, le=500),
    since_hours: int | None = Query(None, ge=1),
    third_party_only: bool = Query(False),
):
    """Audit trail of AI-Job submissions (newest first), read from PostgreSQL.

    `third_party_only=true` excludes our own test/judge accounts, so the result is
    submissions by external identities — the signal that someone (e.g. a judge) ran
    a live test. Degrades to an empty list if the DB is unreachable (never 500s).
    """
    exclude = _KNOWN_IDENTITIES if third_party_only else None
    runs = job_audit.list_recent_job_runs(limit=limit, since_hours=since_hours,
                                          exclude_identities=exclude)
    return {"count": len(runs), "third_party_only": third_party_only, "runs": runs}


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str):
    try:
        nebius.delete_job(job_id)
    except Exception as exc:
        logger.exception("Job deletion failed for %s", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete job: {type(exc).__name__}",
        ) from exc
