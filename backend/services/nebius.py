"""
Job runner abstraction.

Supports Nebius Serverless AI Jobs via the official Python SDK.
Switch JOB_RUNNER_BACKEND env var to 'aws', 'azure', or 'gcp'
and implement the corresponding runner to port to another cloud.

Nebius Python SDK: https://github.com/nebius/pysdk
API reference:     https://nebius.github.io/pysdk/apiReference.html
gRPC host (Jobs + Endpoints): apps.msp.api.nebius.cloud:443
"""

import os
import uuid
from datetime import datetime, timezone

import httpx

JOB_RUNNER_BACKEND = os.getenv("JOB_RUNNER_BACKEND", "nebius")
EXTRACTION_SERVICE_URL = os.getenv("EXTRACTION_SERVICE_URL", "http://extraction:8002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis:8001")

# JobStatus.State enum values from nebius.ai.v1.JobStatus
_JOB_STATE_MAP = {
    0: "pending",    # STATE_UNSPECIFIED
    1: "pending",    # PROVISIONING
    2: "pending",    # STARTING
    3: "running",    # RUNNING
    4: "running",    # CANCELLING
    5: "running",    # DELETING
    6: "completed",  # COMPLETED
    7: "failed",     # FAILED
    8: "failed",     # CANCELLED
    9: "failed",     # ERROR
}


def submit_extraction_job(upload_id: str, period: str) -> dict:
    """Submit a document extraction job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_job(upload_id, period)
    if JOB_RUNNER_BACKEND == "local":
        return _submit_local_job(upload_id, period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_job(upload_id: str, period: str) -> dict:
    from nebius.sdk import SDK
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest, JobSpec
    from nebius.api.nebius.common.v1 import ResourceMetadata
    from google.protobuf.duration_pb2 import Duration

    job_name = f"archon-extract-{period}-{uuid.uuid4().hex[:6]}"

    sdk = SDK()
    try:
        service = JobServiceClient(sdk)
        operation = service.create(
            CreateJobRequest(
                metadata=ResourceMetadata(
                    parent_id=os.environ["NEBIUS_PROJECT_ID"],
                    name=job_name,
                ),
                spec=JobSpec(
                    image=os.environ["EXTRACTION_JOB_IMAGE"],
                    platform=os.getenv("EXTRACTION_JOB_PLATFORM", "gpu-l40s-a"),
                    preset=os.getenv("EXTRACTION_JOB_PRESET", "1gpu-8vcpu-32gb"),
                    subnet_id=os.environ["NEBIUS_SUBNET_ID"],
                    disk=JobSpec.DiskSpec(
                        type=1,  # NETWORK_SSD
                        size_bytes=30 * 1024 * 1024 * 1024,  # 30 GB
                    ),
                    environment_variables=[
                        JobSpec.EnvironmentVariable(name="UPLOAD_ID", value=upload_id),
                        JobSpec.EnvironmentVariable(name="PERIOD", value=period),
                        JobSpec.EnvironmentVariable(name="NEBIUS_BUCKET_NAME", value=os.environ["NEBIUS_BUCKET_NAME"]),
                        JobSpec.EnvironmentVariable(name="STORAGE_ENDPOINT_URL", value=os.environ["STORAGE_ENDPOINT_URL"]),
                        JobSpec.EnvironmentVariable(name="AWS_ACCESS_KEY_ID", value=os.environ["AWS_ACCESS_KEY_ID"]),
                        JobSpec.EnvironmentVariable(name="AWS_SECRET_ACCESS_KEY", value=os.environ["AWS_SECRET_ACCESS_KEY"]),
                        JobSpec.EnvironmentVariable(name="NEBIUS_INFERENCE_BASE_URL", value=os.environ["NEBIUS_INFERENCE_BASE_URL"]),
                        JobSpec.EnvironmentVariable(name="NEBIUS_INFERENCE_API_KEY", value=os.environ["NEBIUS_INFERENCE_API_KEY"]),
                        JobSpec.EnvironmentVariable(name="VISION_MODEL", value=os.getenv("VISION_MODEL", "Qwen/Qwen2-VL-72B-Instruct")),
                    ],
                    timeout=Duration(seconds=7200),  # 2 hours
                ),
            ),
            timeout=120.0,
        ).wait()
        operation.wait_sync()
        job_id = operation.resource_id
    finally:
        sdk.sync_close()

    return {
        "id": job_id,
        "status": "pending",
        "period": period,
        "documentsCount": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "nebius_job_name": job_name,
    }


def _get_nebius_job_status(job_id: str) -> dict:
    from nebius.sdk import SDK
    from nebius.api.nebius.ai.v1 import JobServiceClient, GetJobRequest

    sdk = SDK()
    try:
        service = JobServiceClient(sdk)
        job = service.get(GetJobRequest(id=job_id)).wait()
    finally:
        sdk.sync_close()

    state = job.status.state
    status = _JOB_STATE_MAP.get(state, "pending")

    finished_at = None
    if job.status.HasField("finished_at"):
        finished_at = job.status.finished_at.ToDatetime().isoformat()

    error_message = None
    if status == "failed" and job.status.state_details.message:
        error_message = job.status.state_details.message

    return {
        "id": job_id,
        "status": status,
        "progress": 100 if status == "completed" else (60 if status == "running" else 10),
        "completedAt": finished_at,
        "errorMessage": error_message,
    }


def get_job_status(job_id: str) -> dict:
    """Poll job status from the underlying runner."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _get_nebius_job_status(job_id)
    if JOB_RUNNER_BACKEND == "local":
        return _get_local_job_status(job_id)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def submit_analysis_job(period: str) -> dict:
    """Submit an analysis job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_analysis_job(period)
    if JOB_RUNNER_BACKEND == "local":
        return _submit_local_analysis_job(period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_analysis_job(period: str) -> dict:
    from nebius.sdk import SDK
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest, JobSpec
    from nebius.api.nebius.common.v1 import ResourceMetadata
    from google.protobuf.duration_pb2 import Duration

    job_name = f"archon-analysis-{period}-{uuid.uuid4().hex[:6]}"
    job_id_env = uuid.uuid4().hex[:8]

    sdk = SDK()
    try:
        service = JobServiceClient(sdk)
        operation = service.create(
            CreateJobRequest(
                metadata=ResourceMetadata(
                    parent_id=os.environ["NEBIUS_PROJECT_ID"],
                    name=job_name,
                ),
                spec=JobSpec(
                    image=os.environ["ANALYSIS_JOB_IMAGE"],
                    platform=os.getenv("ANALYSIS_JOB_PLATFORM", "cpu-d3"),
                    preset=os.getenv("ANALYSIS_JOB_PRESET", "4vcpu-16gb"),
                    subnet_id=os.environ["NEBIUS_SUBNET_ID"],
                    disk=JobSpec.DiskSpec(
                        type=1,  # NETWORK_SSD
                        size_bytes=20 * 1024 * 1024 * 1024,  # 20 GB
                    ),
                    environment_variables=[
                        JobSpec.EnvironmentVariable(name="PERIOD", value=period),
                        JobSpec.EnvironmentVariable(name="JOB_ID", value=job_id_env),
                        JobSpec.EnvironmentVariable(name="NEBIUS_BUCKET_NAME", value=os.environ["NEBIUS_BUCKET_NAME"]),
                        JobSpec.EnvironmentVariable(name="STORAGE_ENDPOINT_URL", value=os.environ["STORAGE_ENDPOINT_URL"]),
                        JobSpec.EnvironmentVariable(name="AWS_ACCESS_KEY_ID", value=os.environ["AWS_ACCESS_KEY_ID"]),
                        JobSpec.EnvironmentVariable(name="AWS_SECRET_ACCESS_KEY", value=os.environ["AWS_SECRET_ACCESS_KEY"]),
                        JobSpec.EnvironmentVariable(name="NEBIUS_INFERENCE_BASE_URL", value=os.environ["NEBIUS_INFERENCE_BASE_URL"]),
                        JobSpec.EnvironmentVariable(name="NEBIUS_INFERENCE_API_KEY", value=os.environ["NEBIUS_INFERENCE_API_KEY"]),
                        JobSpec.EnvironmentVariable(name="ANALYSIS_MODEL", value=os.getenv("ANALYSIS_MODEL", "meta-llama/Llama-3.3-70B-Instruct")),
                    ],
                    timeout=Duration(seconds=1800),  # 30 minutes
                ),
            ),
            timeout=120.0,
        ).wait()
        operation.wait_sync()
        job_id = operation.resource_id
    finally:
        sdk.sync_close()

    return {
        "id": job_id,
        "status": "pending",
        "period": period,
        "documentsCount": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "nebius_job_name": job_name,
    }


def _submit_local_analysis_job(period: str) -> dict:
    resp = httpx.post(
        f"{ANALYSIS_SERVICE_URL}/analyze",
        json={"period": period},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": data.get("jobId", "local"),
        "status": "completed",
        "period": period,
        "documentsCount": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def _submit_local_job(upload_id: str, period: str) -> dict:
    resp = httpx.post(
        f"{EXTRACTION_SERVICE_URL}/extract",
        json={"upload_id": upload_id, "period": period},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": data["jobId"],
        "status": "running",
        "period": period,
        "documentsCount": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def _get_local_job_status(job_id: str) -> dict:
    resp = httpx.get(f"{EXTRACTION_SERVICE_URL}/jobs/{job_id}", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    status_map = {"running": "running", "completed": "completed", "failed": "failed"}
    status = status_map.get(data["status"], "pending")
    return {
        "id": job_id,
        "status": status,
        "progress": 100 if status == "completed" else 50,
        "completedAt": data.get("completed_at"),
        "errorMessage": data.get("error") if status == "failed" else None,
    }
