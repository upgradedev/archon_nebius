"""
Local dev HTTP wrapper for the extraction job.

Runs in docker compose as the 'extraction' service on port 8002.
The backend's 'local' job runner POSTs to /extract instead of calling
the Nebius CLI. Not used in production.

Endpoints:
  POST /extract   { upload_id, period }  → { job_id }
  GET  /jobs/{id}                        → { id, status, ... }
  GET  /health
"""

import threading
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Archon Extraction (local dev)", version="1.0.0")

# In-memory job registry  { job_id: { status, created_at, completed_at, error } }
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


class ExtractRequest(BaseModel):
    upload_id: str
    period: str


def _run(job_id: str, upload_id: str, period: str) -> None:
    import os
    os.environ["UPLOAD_ID"] = upload_id
    os.environ["PERIOD"] = period
    try:
        import main as extraction_main
        extraction_main.main()
        with _lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/extract")
def submit(req: ExtractRequest):
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "upload_id": req.upload_id,
            "period": req.period,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        }
    t = threading.Thread(target=_run, args=(job_id, req.upload_id, req.period), daemon=True)
    t.start()
    return {"jobId": job_id, "status": "running"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/health")
def health():
    return {"status": "ok", "service": "archon-extraction-local"}
