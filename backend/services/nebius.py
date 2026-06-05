"""
Job runner abstraction.

Supports Nebius Serverless AI Jobs today.
Switch JOB_RUNNER_BACKEND env var to 'aws', 'azure', or 'gcp'
and implement the corresponding runner to port to another cloud.

Nebius CLI reference:
  https://docs.nebius.com/cli/reference/ai/job
"""

import os
import subprocess
import uuid
import json
from datetime import datetime, timezone


JOB_RUNNER_BACKEND = os.getenv("JOB_RUNNER_BACKEND", "nebius")


def submit_extraction_job(upload_id: str, period: str) -> dict:
    """Submit a document extraction job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_job(upload_id, period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_job(upload_id: str, period: str) -> dict:
    job_name = f"archon-extract-{period}-{uuid.uuid4().hex[:6]}"

    cmd = [
        "nebius", "ai", "job", "create",
        "--name", job_name,
        "--image", os.environ["EXTRACTION_JOB_IMAGE"],
        "--platform", os.getenv("EXTRACTION_JOB_PLATFORM", "gpu-l40s-a"),
        "--preset", os.getenv("EXTRACTION_JOB_PRESET", "1gpu-8vcpu-32gb"),
        "--timeout", "2h",
        "--env", f"UPLOAD_ID={upload_id}",
        "--env", f"PERIOD={period}",
        "--env", f"NEBIUS_BUCKET_NAME={os.environ['NEBIUS_BUCKET_NAME']}",
        "--env", f"STORAGE_ENDPOINT_URL={os.environ['STORAGE_ENDPOINT_URL']}",
        "--env", f"AWS_ACCESS_KEY_ID={os.environ['AWS_ACCESS_KEY_ID']}",
        "--env", f"AWS_SECRET_ACCESS_KEY={os.environ['AWS_SECRET_ACCESS_KEY']}",
        "--env", f"NEBIUS_INFERENCE_BASE_URL={os.environ['NEBIUS_INFERENCE_BASE_URL']}",
        "--env", f"NEBIUS_INFERENCE_API_KEY={os.environ['NEBIUS_INFERENCE_API_KEY']}",
        "--env", f"VISION_MODEL={os.getenv('VISION_MODEL', 'Qwen/Qwen2-VL-72B-Instruct')}",
        "--format", "json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    nebius_job = json.loads(result.stdout)

    return {
        "id": nebius_job.get("id", job_name),
        "status": "pending",
        "period": period,
        "documentsCount": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "nebius_job_name": job_name,
    }


def get_job_status(job_id: str) -> dict:
    """Poll job status from the underlying runner."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _get_nebius_job_status(job_id)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _get_nebius_job_status(job_id: str) -> dict:
    cmd = ["nebius", "ai", "job", "get", "--id", job_id, "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    nebius_job = json.loads(result.stdout)

    # Map Nebius statuses → Archon statuses
    status_map = {
        "QUEUED": "pending",
        "RUNNING": "running",
        "SUCCEEDED": "completed",
        "FAILED": "failed",
        "CANCELLED": "failed",
    }
    raw_status = nebius_job.get("status", {}).get("phase", "QUEUED")
    status = status_map.get(raw_status, "pending")

    return {
        "id": job_id,
        "status": status,
        "progress": 100 if status == "completed" else (60 if status == "running" else 10),
        "completedAt": nebius_job.get("status", {}).get("completedAt"),
        "errorMessage": nebius_job.get("status", {}).get("message") if status == "failed" else None,
    }
