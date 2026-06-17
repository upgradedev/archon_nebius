from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import nebius

router = APIRouter()


class JobRequest(BaseModel):
    uploadId: str
    period: str


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
def submit_job(req: JobRequest):
    try:
        job = nebius.submit_extraction_job(req.uploadId, req.period)
        return JobResponse(**job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str):
    try:
        nebius.delete_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
