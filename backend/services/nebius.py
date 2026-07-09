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
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

JOB_RUNNER_BACKEND = os.getenv("JOB_RUNNER_BACKEND", "nebius")


_REGISTRY_TOKEN_TIMEOUT_SECS = 30


def _get_registry_token() -> str:
    """Return a bearer token for Nebius Container Registry auth.

    Preference order:
    1. Service account credentials (NEBIUS_SA_KEY_B64 + NEBIUS_SA_KEY_ID + NEBIUS_SA_ID)
       — minted through the SAME pysdk service-account bearer that `_make_sdk()`
       already uses successfully for every JobService call. The SDK exchanges the
       SA key for a fresh short-lived IAM token internally (`get_token_sync`).
    2. NEBIUS_IAM_TOKEN env var (12-hour session token, fine for local dev / CLI).
    3. Empty string if nothing is configured (will cause FAILED_PRECONDITION on
       private images — operator must provide credentials).

    When SA vars are present, the SA path is authoritative: a mint failure is
    logged loudly and RAISED. It must NOT silently fall back to a stale/empty
    NEBIUS_IAM_TOKEN — that previous behavior masked broken registry auth behind
    an ephemeral ~12h token (the old code POSTed a JWT to the wrong endpoint,
    https://auth.nebius.com/oauth/token, which returns an HTML login page, so it
    hit JSONDecodeError on every call and fell back invisibly).
    """
    sa_key_b64 = os.getenv("NEBIUS_SA_KEY_B64")
    sa_key_id = os.getenv("NEBIUS_SA_KEY_ID")
    sa_id = os.getenv("NEBIUS_SA_ID")

    if sa_key_b64 and sa_key_id and sa_id:
        sdk = _make_sdk()
        try:
            token = sdk.get_token_sync(_REGISTRY_TOKEN_TIMEOUT_SECS).token
        except Exception:
            logger.exception(
                "Failed to mint registry token via SA pysdk bearer (SA=%s) — "
                "raising rather than falling back to a stale token",
                sa_id,
            )
            raise
        finally:
            sdk.sync_close()
        if not token:
            raise RuntimeError(
                "SA registry token mint returned an empty token — refusing to "
                "submit a job with no registry auth"
            )
        logger.debug("Minted registry token via SA pysdk bearer (SA=%s)", sa_id)
        return token

    iam_token = os.getenv("NEBIUS_IAM_TOKEN", "")
    if iam_token:
        logger.debug("Using NEBIUS_IAM_TOKEN for registry auth (no SA vars set)")
    return iam_token
EXTRACTION_SERVICE_URL = os.getenv("EXTRACTION_SERVICE_URL", "http://extraction:8002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis:8001")


_SA_KEY_PATH = None
_SA_KEY_LOCK = threading.Lock()


def _sa_key_path(sa_key_b64: str) -> str:
    """Return the path to the SA private-key PEM, writing it at most once.

    _make_sdk() is called per job submission and per status poll. The previous
    implementation wrote a fresh delete=False temp file on every call and never
    unlinked it, leaking one temp file per poll. We cache a single PEM file for
    the process lifetime instead (the SDK reads the key lazily from this path,
    so caching the path is safe and preserves the per-call sync_close() contract).
    """
    global _SA_KEY_PATH
    if _SA_KEY_PATH is None:
        with _SA_KEY_LOCK:
            if _SA_KEY_PATH is None:
                pem = base64.b64decode(sa_key_b64).decode()
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
                tmp.write(pem)
                tmp.flush()
                tmp.close()
                _SA_KEY_PATH = tmp.name
    return _SA_KEY_PATH


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
        return SDK(
            service_account_private_key_file_name=_sa_key_path(sa_key_b64),
            service_account_public_key_id=sa_key_id,
            service_account_id=sa_id,
        )

    # Local dev fallback: NEBIUS_IAM_TOKEN session token (expires every 12 h)
    return SDK()

# JobStatus.State enum values from nebius.ai.v1.JobStatus (verified against the
# installed pysdk: PROVISIONING→STARTING→RUNNING→COMPLETED/FAILED/CANCELLED/ERROR).
_STATE_UNSPECIFIED = 0
_STATE_PROVISIONING = 1
_STATE_STARTING = 2
_STATE_RUNNING = 3
_STATE_CANCELLING = 4
_STATE_DELETING = 5
_STATE_COMPLETED = 6
_STATE_FAILED = 7
_STATE_CANCELLED = 8
_STATE_ERROR = 9
_TERMINAL_FAILURE_STATES = frozenset({_STATE_FAILED, _STATE_CANCELLED, _STATE_ERROR})

_JOB_STATE_MAP = {
    _STATE_UNSPECIFIED: "pending",
    _STATE_PROVISIONING: "pending",
    _STATE_STARTING: "pending",
    _STATE_RUNNING: "running",
    _STATE_CANCELLING: "running",
    _STATE_DELETING: "running",
    _STATE_COMPLETED: "completed",
    _STATE_FAILED: "failed",
    _STATE_CANCELLED: "failed",
    _STATE_ERROR: "failed",
}


# ── Compute preset failover ladder (ADR-009) ──────────────────────────────────
# Real Nebius CPU compute, verified in eu-west1 via `nebius compute platform
# list`: `cpu-d3` is the ONLY CPU platform (the sole other platform is the GPU
# `gpu-h200-sxm`). The realistic fallback is therefore LARGER PRESET SIZES within
# cpu-d3 — quota on Nebius AI Jobs can be granted per preset size, so a zero-quota
# `4vcpu-16gb` does not imply zero quota on `8vcpu-32gb`. cpu-d3 offers, in order:
# 4vcpu-16gb, 8vcpu-32gb, 16vcpu-64gb, 32vcpu-128gb, 48vcpu-192gb, 64vcpu-256gb,
# 96vcpu-384gb, 128vcpu-512gb, 160vcpu-640gb, 192vcpu-768gb, 224vcpu-896gb,
# 256vcpu-1024gb.
_DEFAULT_FALLBACK_LADDER = [("cpu-d3", "8vcpu-32gb")]

# Substrings (case-insensitive) that mark a job-creation error as a
# provisioning/capacity precondition — fail over to the next preset. Anything
# else (bad image, malformed spec, auth) is a genuine error and is re-raised.
_PROVISIONING_ERROR_MARKERS = (
    "failed_precondition",
    "resource_exhausted",
    "quota",
    "capacity",
    "unavailable",
    "no available",
    "insufficient",
)

# Provisioning-probe outcome classes.
_PROVISIONED = "provisioned"
_NEVER_PROVISIONED = "never_provisioned"
_APP_FAILURE = "app_failure"


class ComputeCapacityUnavailable(RuntimeError):
    """Every preset in the failover ladder failed to provision.

    The API layer maps this to HTTP 503 so the client receives an actionable
    capacity error instead of a silent stall or a generic 500 — the original
    zero-quota incident was invisible precisely because no such signal existed.
    """

    def __init__(self, name_prefix: str, ladder: list, attempts: list):
        self.name_prefix = name_prefix
        self.ladder = ladder
        self.attempts = attempts
        laddered = ", ".join(f"{p}:{s}" for p, s in ladder) or "(empty ladder)"
        detail = "; ".join(attempts) if attempts else "no ladder entries were attempted"
        super().__init__(
            "processing capacity unavailable — all compute presets failed to "
            f"provision (quota/capacity). Tried [{laddered}]. Details: {detail}"
        )


def _parse_ladder_env() -> list[tuple[str, str]]:
    """Parse JOB_PRESET_LADDER ('platform:preset,platform:preset,...') defensively.

    Malformed entries are logged and skipped; returns [] when unset/empty so the
    caller falls back to the per-job default ladder.
    """
    raw = os.getenv("JOB_PRESET_LADDER", "").strip()
    if not raw:
        return []
    entries: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            logger.warning("Ignoring malformed JOB_PRESET_LADDER entry %r (expected 'platform:preset')", part)
            continue
        platform, preset = (s.strip() for s in part.split(":", 1))
        if platform and preset:
            entries.append((platform, preset))
        else:
            logger.warning("Ignoring malformed JOB_PRESET_LADDER entry %r (empty platform or preset)", part)
            continue
    return entries


def _project_ladder() -> list[str]:
    """Parse NEBIUS_PROJECT_ID_LADDER (comma-separated list of project IDs) defensively.

    If empty or unset, falls back to [os.environ["NEBIUS_PROJECT_ID"]].
    """
    raw = os.getenv("NEBIUS_PROJECT_ID_LADDER", "").strip()
    if not raw:
        default_id = os.getenv("NEBIUS_PROJECT_ID", "").strip()
        return [default_id] if default_id else []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _preset_ladder(default_platform: str, default_preset: str) -> list[tuple[str, str]]:
    """Ordered, bounded, de-duplicated (platform, preset) failover ladder.

    Source of truth is JOB_PRESET_LADDER. When unset, the live per-job
    platform/preset (from EXTRACTION_JOB_* / ANALYSIS_JOB_* env) is rung 1,
    followed by the verified real fallback size(s) within cpu-d3.
    """
    ladder = _parse_ladder_env()
    if not ladder:
        ladder = [(default_platform, default_preset)]
        ladder.extend(_DEFAULT_FALLBACK_LADDER)
    seen: set = set()
    deduped: list[tuple[str, str]] = []
    for entry in ladder:
        if entry not in seen:
            seen.add(entry)
            deduped.append(entry)
    return deduped


def _is_provisioning_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _PROVISIONING_ERROR_MARKERS)


def _provision_probe_secs() -> float:
    """How long to probe a submitted job for a fast provisioning failure."""
    return float(os.getenv("JOB_PROVISION_PROBE_SECS", "30"))


def _provision_poll_secs() -> float:
    return float(os.getenv("JOB_PROVISION_POLL_SECS", "5"))


def _await_provisioning(service, job_id: str) -> str:
    """Bounded probe classifying whether a submitted job actually got compute.

    Returns one of:
      * _PROVISIONED      — compute was allocated (RUNNING / COMPLETED / instances
                            present / started_at set). The job reached real compute,
                            so we return it as pending and let the caller poll it to
                            completion.
      * _NEVER_PROVISIONED— terminal failure with zero instances and never RUNNING,
                            the job vanished mid-provisioning (silent teardown), OR
                            the probe window elapsed while the job was STILL in
                            PROVISIONING with zero instances (the accept-then-stall
                            capacity signature: on a zero-capacity preset the job is
                            accepted but no instance is ever allocated). Caller
                            deletes the scaffolding and fails over to the next preset.
      * _APP_FAILURE      — the job reached compute (RUNNING / instances / started_at)
                            and then failed. This is an application/config bug that
                            would recur identically on every preset, so the caller
                            does NOT fail over (retrying would mask the bug + cost
                            money).

    The primary discriminator is instances-count + terminal-state. Elapsed time is
    the backstop: a job still in PROVISIONING with zero instances at the deadline is
    an accept-then-stall capacity miss (_NEVER_PROVISIONED), not a healthy slow job —
    a preset WITH capacity allocates an instance quickly (the probe returns
    _PROVISIONED the instant one appears), so reaching the deadline with none means
    the preset has no capacity for this job.
    """
    from nebius.api.nebius.ai.v1 import GetJobRequest

    deadline = time.monotonic() + _provision_probe_secs()
    poll = _provision_poll_secs()
    instances_seen = False

    while True:
        try:
            job = service.get(GetJobRequest(id=job_id)).wait()
        except Exception as exc:
            logger.warning("GetJob %s failed during provisioning probe (job may have torn itself down): %s", job_id, exc)
            return _NEVER_PROVISIONED

        status = job.status
        state = status.state
        instances_seen = instances_seen or len(status.instances) > 0
        has_compute = (
            instances_seen
            or state == _STATE_RUNNING
            or status.check_presence("started_at")
        )

        if state == _STATE_COMPLETED or state == _STATE_RUNNING:
            return _PROVISIONED
        if state in _TERMINAL_FAILURE_STATES:
            # No compute ever => capacity miss. Compute existed => app bug.
            return _APP_FAILURE if has_compute else _NEVER_PROVISIONED
        if has_compute:
            # Instances up (STARTING) — capacity confirmed; return and let the
            # caller poll to completion exactly as before.
            return _PROVISIONED
        if time.monotonic() >= deadline:
            # Still PROVISIONING with zero instances at probe end. This is the
            # accept-then-stall capacity signature (#81 gap): the job was accepted
            # but the preset never allocated an instance. A preset WITH capacity
            # allocates quickly and would have returned _PROVISIONED above, so treat
            # this as a capacity miss — delete the scaffolding and fail over to the
            # next rung rather than leaving the job stalled forever in PROVISIONING.
            logger.warning(
                "Job %s still provisioning with 0 instances after %.0fs — "
                "accept-then-stall capacity miss; failing over to next preset",
                job_id, _provision_probe_secs(),
            )
            return _NEVER_PROVISIONED
        time.sleep(poll)


def _job_failure_message(service, job_id: str) -> str:
    try:
        from nebius.api.nebius.ai.v1 import GetJobRequest

        job = service.get(GetJobRequest(id=job_id)).wait()
        return job.status.state_details.message or f"state={job.status.state}"
    except Exception:
        return "unknown"


def _safe_delete_job(service, job_id: str) -> None:
    """Delete never-provisioned scaffolding before trying the next preset."""
    try:
        from nebius.api.nebius.ai.v1 import DeleteJobRequest

        service.delete(DeleteJobRequest(id=job_id)).wait()
        logger.info("Deleted never-provisioned job %s", job_id)
    except Exception:
        logger.warning("Could not delete never-provisioned job %s — continuing", job_id)


def _submit_job_with_failover(name_prefix, period, default_platform, default_preset, build_spec) -> dict:
    """Submit a Nebius AI Job, failing over across projects and compute preset ladders on
    never-provisioned outcomes only.

    build_spec(platform, preset) -> JobSpec. Each ladder entry is tried AT MOST
    ONCE, in order. Fails over ONLY when a job never provisioned (terminal failure
    with zero instances / vanished job / submission-time provisioning error).
    Reaching compute then failing is surfaced immediately (no failover). When the
    whole ladder is exhausted, raises ComputeCapacityUnavailable (→ HTTP 503).
    """
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest
    from nebius.api.nebius.common.v1 import ResourceMetadata

    projects = _project_ladder()
    presets = _preset_ladder(default_platform, default_preset)

    attempts: list[str] = []

    for project_id in projects:
        _delete_nebius_error_jobs(period, name_prefix, project_id)

        for idx, (platform, preset) in enumerate(presets, start=1):
            job_name = f"{name_prefix}-{period}-{uuid.uuid4().hex[:6]}"
            logger.info("Submitting %s in project=%s on platform=%s preset=%s (preset %d/%d)",
                        job_name, project_id, platform, preset, idx, len(presets))
            sdk = _make_sdk()
            try:
                service = JobServiceClient(sdk)
                try:
                    # service.create(...).wait() resolves the create operation and
                    # returns an Operation (NOT the Job proto). The created job's id is
                    # on Operation.resource_id — Operation has no .metadata.
                    operation = service.create(
                        CreateJobRequest(
                            metadata=ResourceMetadata(
                                parent_id=project_id,
                                name=job_name,
                            ),
                            spec=build_spec(platform, preset),
                        ),
                    ).wait()
                except Exception as exc:
                    if _is_provisioning_error(exc):
                        logger.warning(
                            "Project %s, preset %s:%s rejected at submission (provisioning/quota): %s — trying next configuration",
                            project_id, platform, preset, exc,
                        )
                        attempts.append(f"{project_id}:{platform}:{preset} submit-rejected ({exc})")
                        continue
                    logger.exception("Failed to submit %s on %s:%s in project %s", job_name, platform, preset, project_id)
                    raise

                job_id = operation.resource_id
                outcome = _await_provisioning(service, job_id)

                if outcome == _PROVISIONED:
                    logger.info("Job %s provisioned on %s:%s in project=%s (id=%s)", job_name, platform, preset, project_id, job_id)
                    return {
                        "id": job_id,
                        "status": "pending",
                        "period": period,
                        "documentsCount": 0,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                        "nebius_job_name": job_name,
                    }

                if outcome == _APP_FAILURE:
                    msg = _job_failure_message(service, job_id)
                    logger.error(
                        "Job %s failed AFTER provisioning on %s:%s in project=%s — application error, NOT failing over: %s",
                        job_name, platform, preset, project_id, msg,
                    )
                    raise RuntimeError(f"Job {job_name} failed after provisioning on {platform}:{preset} in project {project_id}: {msg}")

                # _NEVER_PROVISIONED — clean up scaffolding, then try the next configuration.
                logger.warning("Job %s never provisioned on %s:%s in project=%s — cleaning up and trying next configuration", job_name, platform, preset, project_id)
                attempts.append(f"{project_id}:{platform}:{preset} never-provisioned")
                _safe_delete_job(service, job_id)
            finally:
                sdk.sync_close()

    # Reconstruct the representation of what was tried for the exception message
    ladder_repr = [(p, pr) for p in projects for (pl, pr) in presets]
    raise ComputeCapacityUnavailable(name_prefix, ladder_repr, attempts)


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
    from nebius.api.nebius.ai.v1 import JobSpec
    from google.protobuf.duration_pb2 import Duration

    # Fetch the registry token once and reuse across ladder attempts (it is a
    # short-lived IAM token; the whole failover completes well within its TTL).
    token = _get_registry_token()

    def build_spec(platform: str, preset: str):
        return JobSpec(
            image=os.environ["EXTRACTION_JOB_IMAGE"],
            platform=platform,
            preset=preset,
            subnet_id=os.environ["NEBIUS_SUBNET_ID"],
            disk=JobSpec.DiskSpec(
                type=1,  # NETWORK_SSD
                size_bytes=30 * 1024 * 1024 * 1024,  # 30 GB
            ),
            registry_credentials=JobSpec.RegistryCredentials(
                username="iam",
                password=token,
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
                JobSpec.EnvironmentVariable(name="VISION_MODEL", value=os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")),
                # Document-at-rest encryption (KMS envelope) must reach the
                # extraction Job so it can decrypt envelope-encrypted raw docs.
                # The read path only decrypts objects carrying the magic header,
                # so all-empty values are a safe no-op (feature OFF by default).
                # The KMS DECRYPT call needs Nebius auth, so the SA credentials
                # (the same identity that launches this Job) are forwarded too.
                JobSpec.EnvironmentVariable(name="DOC_ENCRYPTION_ENABLED", value=os.getenv("DOC_ENCRYPTION_ENABLED", "")),
                JobSpec.EnvironmentVariable(name="DOC_ENCRYPTION_KMS_KEY_ID", value=os.getenv("DOC_ENCRYPTION_KMS_KEY_ID", "")),
                JobSpec.EnvironmentVariable(name="NEBIUS_SA_KEY_B64", value=os.getenv("NEBIUS_SA_KEY_B64", "")),
                JobSpec.EnvironmentVariable(name="NEBIUS_SA_KEY_ID", value=os.getenv("NEBIUS_SA_KEY_ID", "")),
                JobSpec.EnvironmentVariable(name="NEBIUS_SA_ID", value=os.getenv("NEBIUS_SA_ID", "")),
            ],
            timeout=Duration(seconds=7200),  # 2 hours
        )

    return _submit_job_with_failover(
        name_prefix="archon-extract",
        period=period,
        default_platform=os.getenv("EXTRACTION_JOB_PLATFORM", "cpu-d3"),
        default_preset=os.getenv("EXTRACTION_JOB_PRESET", "4vcpu-16gb"),
        build_spec=build_spec,
    )


def _delete_nebius_error_jobs(period: str, prefix: str, project_id: str = None) -> None:
    """List all jobs whose name starts with prefix-period and delete ERROR/FAILED ones."""
    from nebius.api.nebius.ai.v1 import JobServiceClient, ListJobsRequest, DeleteJobRequest

    if project_id is None:
        project_id = os.environ.get("NEBIUS_PROJECT_ID", "")
    if not project_id:
        return

    sdk = _make_sdk()
    try:
        service = JobServiceClient(sdk)
        result = service.list(
            ListJobsRequest(parent_id=project_id)
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
                logger.info("Deleting stale %s job %s (state=%s) in project=%s", prefix, job_id, state, project_id)
                try:
                    service.delete(DeleteJobRequest(id=job_id)).wait()
                except Exception:
                    logger.warning("Could not delete job %s — skipping", job_id)
    except Exception:
        logger.warning("Could not sweep stale jobs for period %s in project=%s — continuing", period, project_id)
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
    # pysdk JobStatus is a wrapper (not a raw protobuf): use check_presence(),
    # and finished_at is a python datetime (no .ToDatetime()).
    if job.status.check_presence("finished_at"):
        fa = job.status.finished_at
        finished_at = fa.isoformat() if hasattr(fa, "isoformat") else str(fa)

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
    from nebius.api.nebius.ai.v1 import JobSpec
    from google.protobuf.duration_pb2 import Duration

    job_id_env = uuid.uuid4().hex[:8]
    token = _get_registry_token()

    def build_spec(platform: str, preset: str):
        return JobSpec(
            image=os.environ["ANALYSIS_JOB_IMAGE"],
            platform=platform,
            preset=preset,
            subnet_id=os.environ["NEBIUS_SUBNET_ID"],
            disk=JobSpec.DiskSpec(
                type=1,  # NETWORK_SSD
                size_bytes=20 * 1024 * 1024 * 1024,  # 20 GB
            ),
            registry_credentials=JobSpec.RegistryCredentials(
                username="iam",
                password=token,
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
        )

    return _submit_job_with_failover(
        name_prefix="archon-analysis",
        period=period,
        default_platform=os.getenv("ANALYSIS_JOB_PLATFORM", "cpu-d3"),
        default_preset=os.getenv("ANALYSIS_JOB_PRESET", "4vcpu-16gb"),
        build_spec=build_spec,
    )


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
