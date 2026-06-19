"""
Job runner abstraction.

Supports Nebius Serverless AI Jobs via the official Python SDK.
Switch JOB_RUNNER_BACKEND env var to 'aws', 'azure', or 'gcp'
and implement the corresponding runner to port to another cloud.

Nebius Python SDK: https://github.com/nebius/pysdk
API reference:     https://nebius.github.io/pysdk/apiReference.html
gRPC host (Jobs + Endpoints): apps.msp.api.nebius.cloud:443
"""

import base64
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone

import httpx
import requests

logger = logging.getLogger(__name__)

JOB_RUNNER_BACKEND = os.getenv("JOB_RUNNER_BACKEND", "nebius")


def _get_registry_token() -> str:
    """Return a bearer token for Nebius Container Registry auth.

    Preference order:
    1. Service account credentials (NEBIUS_SA_KEY_B64 + NEBIUS_SA_KEY_ID + NEBIUS_SA_ID)
       — generates a fresh short-lived IAM token via JWT bearer flow.
    2. NEBIUS_IAM_TOKEN env var (12-hour session token, fine for local dev).
    3. Empty string if nothing is configured (will cause FAILED_PRECONDITION on
       private images — operator must provide credentials).
    """
    sa_key_b64 = os.getenv("NEBIUS_SA_KEY_B64")
    sa_key_id = os.getenv("NEBIUS_SA_KEY_ID")
    sa_id = os.getenv("NEBIUS_SA_ID")

    if sa_key_b64 and sa_key_id and sa_id:
        try:
            import jwt  # PyJWT

            pem = base64.b64decode(sa_key_b64).decode()
            now = int(time.time())
            aud = "https://auth.nebius.com/oauth/token"
            payload = {
                "iss": sa_id,
                "sub": sa_id,
                "aud": aud,
                "iat": now,
                "exp": now + 600,
            }
            signed_jwt = jwt.encode(
                payload,
                pem,
                algorithm="RS256",
                headers={"kid": sa_key_id},
            )
            resp = requests.post(
                aud,
                json={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": signed_jwt,
                },
                timeout=10,
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]
            logger.debug("Fetched fresh IAM token for registry auth (SA=%s)", sa_id)
            return token
        except Exception:
            logger.exception("Failed to generate IAM token from SA credentials — falling back to NEBIUS_IAM_TOKEN")

    iam_token = os.getenv("NEBIUS_IAM_TOKEN", "")
    if iam_token:
        logger.debug("Using NEBIUS_IAM_TOKEN for registry auth")
    return iam_token
EXTRACTION_SERVICE_URL = os.getenv("EXTRACTION_SERVICE_URL", "http://extraction:8002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis:8001")


def _make_sdk():
    """Return a Nebius SDK instance.

    Prefers service account credentials (NEBIUS_SA_KEY_B64 + NEBIUS_SA_KEY_ID +
    NEBIUS_SA_ID) which never expire. Falls back to NEBIUS_IAM_TOKEN session
    token for local dev where a service account is not configured.
    """
    from nebius.sdk import SDK

    sa_key_b64 = os.getenv("NEBIUS_SA_KEY_B64")
    sa_key_id = os.getenv("NEBIUS_SA_KEY_ID")
    sa_id = os.getenv("NEBIUS_SA_ID")

    if sa_key_b64 and sa_key_id and sa_id:
        pem = base64.b64decode(sa_key_b64).decode()
        # Write PEM to a temp file — SDK requires a file path, not a string
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
        tmp.write(pem)
        tmp.flush()
        tmp.close()
        return SDK(
            service_account_private_key_file_name=tmp.name,
            service_account_public_key_id=sa_key_id,
            service_account_id=sa_id,
        )

    # Local dev fallback: NEBIUS_IAM_TOKEN session token (expires every 12 h)
    return SDK()

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


def check_nebius_permissions() -> dict:
    """Smoke-test SA credentials at startup. Returns {"ok": True} or {"ok": False, "error": "..."}."""
    if JOB_RUNNER_BACKEND != "nebius":
        return {"ok": True, "backend": JOB_RUNNER_BACKEND}
    from nebius.api.nebius.ai.v1 import JobServiceClient, ListJobsRequest

    try:
        sdk = _make_sdk()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        svc = JobServiceClient(sdk)
        svc.list(ListJobsRequest(parent_id=os.environ["NEBIUS_PROJECT_ID"])).wait()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        sdk.sync_close()


def submit_extraction_job(upload_id: str, period: str) -> dict:
    """Submit a document extraction job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_job(upload_id, period)
    if JOB_RUNNER_BACKEND == "local":
        return _submit_local_job(upload_id, period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_job(upload_id: str, period: str) -> dict:
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest, JobSpec
    from nebius.api.nebius.common.v1 import ResourceMetadata
    from google.protobuf.duration_pb2 import Duration

    job_name = f"archon-extract-{period}-{uuid.uuid4().hex[:6]}"

    _delete_nebius_error_jobs(period, "archon-extract")

    sdk = _make_sdk()
    try:
        service = JobServiceClient(sdk)
        # .wait() resolves the async operation and returns the Job proto directly.
        # Do NOT call .wait_sync() after — that doubles the wait on an already-resolved result.
        job = service.create(
            CreateJobRequest(
                metadata=ResourceMetadata(
                    parent_id=os.environ["NEBIUS_PROJECT_ID"],
                    name=job_name,
                ),
                spec=JobSpec(
                    image=os.environ["EXTRACTION_JOB_IMAGE"],
                    platform=os.getenv("EXTRACTION_JOB_PLATFORM", "cpu-d3"),
                    preset=os.getenv("EXTRACTION_JOB_PRESET", "4vcpu-16gb"),
                    subnet_id=os.environ["NEBIUS_SUBNET_ID"],
                    disk=JobSpec.DiskSpec(
                        type=1,  # NETWORK_SSD
                        size_bytes=30 * 1024 * 1024 * 1024,  # 30 GB
                    ),
                    registry_credentials=[
                        JobSpec.RegistryCredentials(
                            username="iam",
                            password=_get_registry_token(),
                        )
                    ],
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
        ).wait()
        job_id = job.metadata.id
        logger.info("Extraction job created: %s (id=%s)", job_name, job_id)
    except Exception:
        logger.exception("Failed to submit extraction job %s", job_name)
        raise
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


def _delete_nebius_error_jobs(period: str, prefix: str) -> None:
    """List all jobs whose name starts with prefix-period and delete ERROR/FAILED ones."""
    from nebius.api.nebius.ai.v1 import JobServiceClient, ListJobsRequest, DeleteJobRequest

    sdk = _make_sdk()
    try:
        service = JobServiceClient(sdk)
        result = service.list(
            ListJobsRequest(parent_id=os.environ["NEBIUS_PROJECT_ID"])
        ).wait()
        name_prefix = f"{prefix}-{period}-"
        for job in result.items:
            name = job.metadata.name or ""
            if not name.startswith(name_prefix):
                continue
            state = job.status.state
            # States 7=FAILED, 8=CANCELLED, 9=ERROR
            if state in (7, 8, 9):
                job_id = job.metadata.id
                logger.info("Deleting stale %s job %s (state=%s)", prefix, job_id, state)
                try:
                    service.delete(DeleteJobRequest(id=job_id)).wait()
                except Exception:
                    logger.warning("Could not delete job %s — skipping", job_id)
    except Exception:
        logger.warning("Could not sweep stale jobs for period %s — continuing", period)
    finally:
        sdk.sync_close()


def delete_job(job_id: str) -> None:
    """Delete a Nebius job by ID (used to clear ERROR state jobs from the UI)."""
    if JOB_RUNNER_BACKEND != "nebius":
        return
    from nebius.api.nebius.ai.v1 import JobServiceClient, DeleteJobRequest

    sdk = _make_sdk()
    try:
        service = JobServiceClient(sdk)
        service.delete(DeleteJobRequest(id=job_id)).wait()
        logger.info("Deleted job %s", job_id)
    finally:
        sdk.sync_close()


def _get_nebius_job_status(job_id: str) -> dict:
    from nebius.api.nebius.ai.v1 import JobServiceClient, GetJobRequest

    sdk = _make_sdk()
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
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest, JobSpec
    from nebius.api.nebius.common.v1 import ResourceMetadata
    from google.protobuf.duration_pb2 import Duration

    job_name = f"archon-analysis-{period}-{uuid.uuid4().hex[:6]}"
    job_id_env = uuid.uuid4().hex[:8]

    _delete_nebius_error_jobs(period, "archon-analysis")

    sdk = _make_sdk()
    try:
        service = JobServiceClient(sdk)
        job = service.create(
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
                    registry_credentials=[
                        JobSpec.RegistryCredentials(
                            username="iam",
                            password=_get_registry_token(),
                        )
                    ],
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
        ).wait()
        job_id = job.metadata.id
        logger.info("Analysis job created: %s (id=%s)", job_name, job_id)
    except Exception:
        logger.exception("Failed to submit analysis job %s", job_name)
        raise
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
