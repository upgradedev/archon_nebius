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
from dataclasses import dataclass
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

    reg_password = os.getenv("NEBIUS_REGISTRY_PASSWORD", "")
    if reg_password:
        logger.debug("Using NEBIUS_REGISTRY_PASSWORD for registry auth")
        return reg_password

    iam_token = os.getenv("NEBIUS_IAM_TOKEN", "")
    if iam_token:
        logger.debug("Using NEBIUS_IAM_TOKEN for registry auth (no SA/registry_password vars set)")
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
_PENDING_PROVISION = "pending_provision"
_NEVER_PROVISIONED = "never_provisioned"
_APP_FAILURE = "app_failure"


@dataclass(frozen=True)
class _ProjectConfig:
    """Project-local resources required to place a Serverless AI Job."""

    project_id: str
    region: str
    subnet_id: str


_REQUIRED_COMPUTE_QUOTAS = (
    "compute.instance.count",
    "compute.instance.non-gpu.vcpu",
)


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


class NoJobsQuota(ComputeCapacityUnavailable):
    """A pre-flight quota check proved AI-Jobs quota is a hard 0 for the target
    platform+region, so a submission would sit in PROVISIONING and then FAIL
    (~30 min) with zero chance of launching. Mapped to the same HTTP 503, but
    raised BEFORE submitting so the caller gets an instant, named answer.

    Note on 'chance of launch': Nebius' Capacity Advisor (HIGH/MEDIUM/LOW) is
    GPU-VM-only and explicitly excludes cpu-d3 and AI Jobs, so there is no
    probabilistic capacity signal for this workload — a CPU Job either has quota
    (>0, launches) or does not (==0, never launches). This check reads that
    deterministic quota via QuotaAllowanceService.
    """

    def __init__(self, platform: str, region: str, limit):
        self.platform = platform
        self.region = region
        super(ComputeCapacityUnavailable, self).__init__(
            f"no AI-Jobs quota for {platform} in region {region} "
            f"(limit={limit}). Request a quota increase in the Nebius Console "
            f"(project quotas) or email serverlesschallenge@nebius.com."
        )


def _target_region() -> str:
    """Legacy/default region used when per-project configuration is absent."""
    return os.getenv("NEBIUS_REGION", "eu-west1").strip() or "eu-west1"


def _jobs_quota_state(project_id: str, region: str, platform: str) -> tuple[str, object]:
    """Best-effort compute quota lookup for a project and region.

    Returns (state, limit) where state is:
      * "zero"      — either required quota has no remaining allowance;
      * "available" — both required quotas have explicit positive headroom;
      * "unknown"   — a quota is defaulted/absent, or lookup failed.

    Serverless CPU Jobs consume both ``compute.instance.count`` and
    ``compute.instance.non-gpu.vcpu``. A quota allowance whose ``spec.limit`` is
    ``None`` represents the provider default, not a confirmed zero, so it is
    deliberately classified as unknown. Explicit limits account for current
    ``status.usage``. Any uncertainty remains fail-open.
    """
    try:
        from nebius.api.nebius.quotas.v1 import (
            QuotaAllowanceServiceClient,
            ListQuotaAllowancesRequest,
        )
    except Exception as exc:  # SDK without quotas API
        logger.info("Quota pre-flight unavailable (SDK): %s", exc)
        return "unknown", None

    try:
        sdk = _make_sdk()
        svc = QuotaAllowanceServiceClient(sdk)
        # Quota routing is project-specific. Querying the tenant for each project
        # would return the same allowance list and make the project ladder unable
        # to distinguish where capacity actually exists.
        resp = svc.list(ListQuotaAllowancesRequest(parent_id=project_id)).wait()
        observations: dict[str, list[tuple[str, int | None]]] = {
            name: [] for name in _REQUIRED_COMPUTE_QUOTAS
        }
        for item in getattr(resp, "items", []) or []:
            spec = getattr(item, "spec", None)
            status = getattr(item, "status", None)
            if spec is None:
                continue
            if (getattr(spec, "region", "") or "") != region:
                continue

            raw_name = str(getattr(getattr(item, "metadata", None), "name", "") or "").strip().lower()
            quota_name = next(
                (
                    required
                    for required in _REQUIRED_COMPUTE_QUOTAS
                    if raw_name == required or raw_name.endswith(f"/{required}")
                ),
                None,
            )
            if quota_name is None:
                continue

            limit = getattr(spec, "limit", None)
            if limit is None:
                # An omitted limit means "provider default" in the allowance API.
                # It must never be interpreted as the protobuf scalar default 0.
                observations[quota_name].append(("unknown", None))
                continue

            try:
                explicit_limit = int(limit)
                usage = getattr(status, "usage", 0) if status is not None else 0
                explicit_usage = int(usage or 0)
            except (TypeError, ValueError):
                observations[quota_name].append(("unknown", None))
                continue

            remaining = max(explicit_limit - explicit_usage, 0)
            observations[quota_name].append(
                ("available" if remaining > 0 else "zero", remaining)
            )

        quota_states: dict[str, str] = {}
        headroom: dict[str, int] = {}
        for quota_name, rows in observations.items():
            # Ambiguous duplicate rows fail open: a positive explicit allowance
            # wins, followed by an unknown/default row, and only unanimous explicit
            # exhaustion is a confirmed zero.
            available = [remaining for state, remaining in rows if state == "available"]
            if available:
                quota_states[quota_name] = "available"
                headroom[quota_name] = max(available)
            elif any(state == "unknown" for state, _ in rows) or not rows:
                quota_states[quota_name] = "unknown"
            else:
                quota_states[quota_name] = "zero"

        if any(state == "zero" for state in quota_states.values()):
            return "zero", 0
        if all(quota_states.get(name) == "available" for name in _REQUIRED_COMPUTE_QUOTAS):
            return "available", min(headroom.values())
        return "unknown", None
    except Exception as exc:
        logger.info(
            "Quota pre-flight failed for project=%s region=%s platform=%s (fail-open): %s",
            project_id, region, platform, exc,
        )
        return "unknown", None
    finally:
        if "sdk" in locals():
            sdk.sync_close()


def _preflight_jobs_quota(project_id: str, platform: str) -> None:
    """Raise NoJobsQuota if quota is a confirmed hard 0. Opt-in and fail-open.

    Disabled unless JOB_QUOTA_PREFLIGHT is truthy — the exact quota resource name
    must be confirmed against a live tenant (real credentials) before this can
    safely short-circuit submissions. Off by default = behaviour identical to
    today; on = the 30-minute provision-then-FAIL becomes an instant, named 503.
    """
    if os.getenv("JOB_QUOTA_PREFLIGHT", "").strip().lower() not in ("1", "true", "yes", "on"):
        return
    region = _project_config_for(project_id).region
    state, limit = _jobs_quota_state(project_id, region, platform)
    if state == "zero":
        logger.warning(
            "Quota pre-flight: %s AI-Jobs quota in %s is 0 — refusing to submit "
            "(would provision then FAIL). Raising 503.", platform, region,
        )
        raise NoJobsQuota(platform, region, limit)
    logger.info("Quota pre-flight for %s in %s: %s (proceeding)", platform, region, state)


def _preflight_enabled() -> bool:
    return os.getenv("JOB_QUOTA_PREFLIGHT", "").strip().lower() in ("1", "true", "yes", "on")


def _route_projects_by_quota(
    projects: list[str], presets: list[tuple[str, str]], region: str | None = None
) -> tuple[list[str], dict[tuple[str, str], str]]:
    """Active quota-driven routing across the project ladder (opt-in).

    Supersedes the single-project `_preflight_jobs_quota` gate for the submit path:
    instead of only raising on the FIRST project's confirmed zero (which would kill
    a submission that could succeed on a later project), it queries the quota API
    for every (project, ladder-platform) pair and:

      * ORDERS projects available-first, then unknown;
      * DROPS a project that is a confirmed hard-zero on EVERY ladder platform
        (submitting there only PROVISIONS-then-FAILs for ~30 min);
      * returns a per-(project, platform) verdict so the submit loop can also SKIP
        a single zero rung inside an otherwise-viable project.

    Returns (ordered_projects, verdict). When the pre-flight is disabled it returns
    (projects, {}) and performs NO quota lookups — behaviour identical to before.
    FAIL-OPEN by contract: any 'unknown' verdict keeps the project/rung in play, so
    a quota API that is missing, unauthorized, or silent can only ever REORDER, and
    can drop a rung only on a *confirmed* zero.
    """
    if not _preflight_enabled():
        return list(projects), {}

    platforms = list(dict.fromkeys(pl for pl, _ in presets))
    project_regions = {
        project_id: _project_config_for(project_id, fallback_region=region).region
        for project_id in projects
    }
    verdict: dict[tuple[str, str], str] = {}
    for project_id in projects:
        for platform in platforms:
            verdict[(project_id, platform)] = _jobs_quota_state(
                project_id, project_regions[project_id], platform
            )[0]

    def rank(project_id: str) -> int:
        states = [verdict[(project_id, pl)] for pl in platforms]
        if any(s == "available" for s in states):
            return 0
        if any(s == "unknown" for s in states):
            return 1
        return 2  # confirmed zero on every ladder platform

    ordered = [p for p in sorted(projects, key=rank) if rank(p) < 2]
    dropped = [p for p in projects if rank(p) >= 2]
    if dropped:
        logger.warning(
            "Quota routing: dropping project(s) %s — confirmed exhausted compute "
            "quota in their configured regions on every ladder platform (%s)",
            [f"{p}@{project_regions[p]}" for p in dropped], ", ".join(platforms),
        )
    if ordered:
        logger.info(
            "Quota routing: trying projects in order %s",
            [f"{p}@{project_regions[p]}" for p in ordered],
        )
    return ordered, verdict


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


def _legacy_project_ladder() -> list[str]:
    """Return the legacy project-id-only ladder, preserving order."""
    raw = os.getenv("NEBIUS_PROJECT_ID_LADDER", "").strip()
    if not raw:
        default_id = os.getenv("NEBIUS_PROJECT_ID", "").strip()
        return [default_id] if default_id else []
    return list(dict.fromkeys(p.strip() for p in raw.split(",") if p.strip()))


def _parse_project_configs() -> list[_ProjectConfig]:
    """Parse ``project=region=subnet`` entries from NEBIUS_PROJECT_CONFIGS.

    Malformed or duplicate entries are ignored with a warning. Returning an empty
    list lets callers fall back to the legacy single-region environment contract.
    """
    raw = os.getenv("NEBIUS_PROJECT_CONFIGS", "").strip()
    if not raw:
        return []

    configs: list[_ProjectConfig] = []
    seen: set[str] = set()
    for raw_entry in raw.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split("=")]
        if len(parts) != 3 or not all(parts):
            logger.warning(
                "Ignoring malformed NEBIUS_PROJECT_CONFIGS entry %r "
                "(expected project=region=subnet)",
                entry,
            )
            continue
        project_id, region, subnet_id = parts
        if project_id in seen:
            logger.warning(
                "Ignoring duplicate NEBIUS_PROJECT_CONFIGS project %r", project_id
            )
            continue
        seen.add(project_id)
        configs.append(_ProjectConfig(project_id, region, subnet_id))
    return configs


def _project_configs() -> list[_ProjectConfig]:
    """Return explicit project-local configs or synthesize the legacy layout."""
    explicit = _parse_project_configs()
    if explicit:
        return explicit

    region = _target_region()
    subnet_id = os.getenv("NEBIUS_SUBNET_ID", "").strip()
    return [
        _ProjectConfig(project_id, region, subnet_id)
        for project_id in _legacy_project_ladder()
    ]


def _project_ladder() -> list[str]:
    """Return configured project IDs in routing order."""
    return [config.project_id for config in _project_configs()]


def _project_config_for(
    project_id: str, fallback_region: str | None = None
) -> _ProjectConfig:
    """Resolve a project's local region/subnet with legacy env compatibility."""
    for config in _project_configs():
        if config.project_id == project_id:
            return config
    return _ProjectConfig(
        project_id=project_id,
        region=fallback_region or _target_region(),
        subnet_id=os.getenv("NEBIUS_SUBNET_ID", "").strip(),
    )


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
    """How long to probe a submitted job for a fast provisioning outcome.

    Kept comfortably UNDER the Firebase BFF ~60s request ceiling so the submit
    POST returns (with the job as pending) before the BFF times out and the
    frontend retries — a retry that raced a still-open ~90s probe used to hit the
    backend before the idempotency marker was written, spawning a duplicate. The
    marker is now written the instant the job is created (before the probe), so the
    window is closed either way; a shorter probe just removes the retry entirely in
    the common case. A slow provision returns pending and is polled to completion,
    so the probe no longer needs to be generous.
    """
    return float(os.getenv("JOB_PROVISION_PROBE_SECS", "25"))


def _provision_poll_secs() -> float:
    return float(os.getenv("JOB_PROVISION_POLL_SECS", "5"))


def _await_provisioning(service, job_id: str) -> str:
    """Bounded probe classifying whether a submitted job actually got compute.

    Returns one of:
      * _PROVISIONED      — compute was allocated (RUNNING / COMPLETED / instances
                            present / started_at set). The job reached real compute,
                            so we return it as pending and let the caller poll it to
                            completion.
      * _PENDING_PROVISION— the probe window elapsed while the job was STILL in
                            PROVISIONING with zero instances and NO terminal state.
                            Nebius AI Jobs legitimately take MINUTES to provision
                            (~5 min cold start), far longer than the probe window, so
                            this is a HEALTHY slow start, not a failure. We return it
                            as pending WITHOUT deleting it: the caller keeps THIS job
                            and the frontend polls it to completion on the same
                            machine. Never fail over here — killing a healthy slow
                            provision and spawning a new preset job was the bug that
                            walked the whole ladder (CPU->GPU) recreating jobs.
      * _NEVER_PROVISIONED— an UNAMBIGUOUS never-provisioned signal: a terminal
                            failure (`FAILED`/`CANCELLED`/`ERROR`) with zero instances
                            and never RUNNING, or the job vanished mid-provisioning
                            (GetJob raised — silent teardown). Caller deletes the
                            scaffolding and fails over to the next preset.
      * _APP_FAILURE      — the job reached compute (RUNNING / instances / started_at)
                            and then failed. This is an application/config bug that
                            would recur identically on every preset, so the caller
                            does NOT fail over (retrying would mask the bug + cost
                            money).

    The discriminator is instances-count + terminal-state, NEVER elapsed time. A job
    stuck in PROVISIONING at the deadline is NOT presumed dead — we cannot tell a
    healthy slow provision from a zero-capacity stall by the clock, so we refuse to
    guess: we return _PENDING_PROVISION and keep the job. Failover is reserved for
    the two signals that are genuinely unambiguous (terminal failure with zero
    instances, or a vanished job) plus the submission-time quota/precondition error
    handled by the caller.
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
            # Still PROVISIONING with zero instances at probe end, and NOT in a
            # terminal state. Nebius Jobs take minutes to provision, so this is a
            # healthy slow start — NOT a capacity miss. Return it as pending and let
            # the caller keep THIS job (the frontend polls the same job id to
            # completion). We deliberately do NOT delete it or fail over: doing so
            # was the days-costly bug that killed healthy slow provisions at ~30s and
            # spawned a fresh preset job each time, walking the whole ladder.
            logger.warning(
                "Job %s still provisioning with 0 instances after %.0fs — healthy "
                "slow start (Jobs take minutes); returning it as pending and keeping "
                "it. The caller polls THIS job to completion; no failover, no new job.",
                job_id, _provision_probe_secs(),
            )
            return _PENDING_PROVISION
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


def _build_spec_for_project(build_spec, project_id: str, platform: str, preset: str):
    """Call the project-aware builder while retaining old demo/test adapters.

    Production builders receive all three values. The signature check keeps the
    published two-argument offline failover demo working without catching a
    TypeError raised *inside* a real builder.
    """
    import inspect

    try:
        parameters = inspect.signature(build_spec).parameters.values()
    except (TypeError, ValueError):
        return build_spec(project_id, platform, preset)
    positional = [
        parameter for parameter in parameters
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if not any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters) \
            and len(positional) < 3:
        logger.debug("Calling legacy two-argument JobSpec builder")
        return build_spec(platform, preset)
    return build_spec(project_id, platform, preset)


def _submit_job_with_failover(name_prefix, period, default_platform, default_preset, build_spec, on_created=None) -> dict:
    """Submit a Nebius AI Job, failing over across projects and compute preset ladders on
    never-provisioned outcomes only.

    build_spec(project_id, platform, preset) -> JobSpec. on_created(job_dict), if given, is
    invoked the INSTANT a job is created (right after create succeeds, BEFORE the
    provisioning probe) with {id, nebius_job_name, period, createdAt} — used to
    persist the idempotency marker immediately so a retry that races the still-open
    probe finds it and dedupes instead of spawning a duplicate.

    Each ladder entry is tried AT MOST
    ONCE, in order. Fails over ONLY when a job is UNAMBIGUOUSLY never-provisioned
    (terminal failure with zero instances / vanished job / submission-time
    provisioning error). A job that is still PROVISIONING at the probe deadline is a
    healthy slow start (Jobs take minutes) — it is returned as pending on THE SAME
    machine, never deleted, never failed over (the caller/frontend polls that job id
    to completion). Reaching compute then failing is surfaced immediately (no
    failover). When the whole ladder is exhausted, raises ComputeCapacityUnavailable
    (→ HTTP 503).
    """
    from nebius.api.nebius.ai.v1 import JobServiceClient, CreateJobRequest
    from nebius.api.nebius.common.v1 import ResourceMetadata

    candidate_projects = _project_ladder()
    presets = _preset_ladder(default_platform, default_preset)

    # Active quota-driven routing (opt-in via JOB_QUOTA_PREFLIGHT, fail-open):
    # order projects available-first, drop projects that are a confirmed hard 0 on
    # every ladder platform, and yield a per-(project, platform) verdict so the loop
    # can skip a single zero rung. A submission to zero-quota compute only
    # PROVISIONS-then-FAILs (~30 min); routing turns that into an instant answer.
    # No-op + no quota lookups when disabled — identical behaviour to before.
    projects, quota_verdict = _route_projects_by_quota(candidate_projects, presets)
    if _preflight_enabled() and candidate_projects and not projects:
        # Every candidate project is a confirmed hard 0 on every ladder platform —
        # instant, named 503 instead of a 30-minute doomed provision.
        regions = ",".join(
            dict.fromkeys(_project_config_for(project_id).region for project_id in candidate_projects)
        )
        raise NoJobsQuota(default_platform, regions or _target_region(), 0)

    attempts: list[str] = []
    submitted_any = False

    for project_id in projects:
        _delete_nebius_error_jobs(period, name_prefix, project_id)

        for idx, (platform, preset) in enumerate(presets, start=1):
            if quota_verdict.get((project_id, platform)) == "zero":
                # Viable project on another platform, but THIS rung is a confirmed
                # zero — skip it rather than spend ~30 min provisioning-then-failing.
                logger.info(
                    "Skipping %s:%s in project=%s — confirmed 0 AI-Jobs quota (pre-flight)",
                    platform, preset, project_id,
                )
                attempts.append(f"{project_id}:{platform}:{preset} skipped-zero-quota")
                continue
            submitted_any = True
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
                            spec=_build_spec_for_project(
                                build_spec, project_id, platform, preset
                            ),
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
                if on_created is not None:
                    # Persist the idempotency marker the instant the job exists —
                    # BEFORE the (bounded) probe — so a retry that races the still-open
                    # submit finds the marker and dedupes to THIS job. A marker that
                    # ends up pointing at a job we then delete (never-provisioned
                    # failover) is self-correcting: the next rung's create overwrites
                    # it, and _existing_live_job treats a vanished job as "resubmit".
                    on_created({
                        "id": job_id,
                        "nebius_job_name": job_name,
                        "period": period,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    })
                outcome = _await_provisioning(service, job_id)

                if outcome in (_PROVISIONED, _PENDING_PROVISION):
                    if outcome == _PROVISIONED:
                        logger.info("Job %s provisioned on %s:%s in project=%s (id=%s)", job_name, platform, preset, project_id, job_id)
                    else:
                        # Healthy slow start — keep THIS job, do NOT delete or fail
                        # over. The caller polls this job id to completion.
                        logger.warning(
                            "Job %s still provisioning on %s:%s in project=%s (id=%s) — "
                            "returning it as pending; polling continues on the SAME job "
                            "(no failover, no duplicate job).",
                            job_name, platform, preset, project_id, job_id,
                        )
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

    # If routing left at least one viable project but every rung in it was skipped
    # as a confirmed zero, that is still a quota-zero outcome — surface the named
    # 503, not a generic capacity error.
    if _preflight_enabled() and projects and not submitted_any:
        regions = ",".join(
            dict.fromkeys(_project_config_for(project_id).region for project_id in projects)
        )
        raise NoJobsQuota(default_platform, regions or _target_region(), 0)

    # Reconstruct the representation of what was tried for the exception message
    ladder_repr = [(p, pr) for p in projects for (pl, pr) in presets]
    raise ComputeCapacityUnavailable(name_prefix, ladder_repr, attempts)


# ── Idempotent submit (dedupe per key) ────────────────────────────────────────
# A submit is keyed by a durable S3 marker so a retry (frontend cold-start retry,
# double-click, or a re-fired request) returns the SAME job instead of spawning a
# duplicate. Extraction is keyed by (upload_id, period); analysis by period. The
# marker holds {job_id, nebius_job_name, period, createdAt}. All storage access is
# fully defensive: a missing/unreadable marker or an undeterminable status degrades
# to "no prior job — submit", never a crash, so a storage outage only forfeits
# dedupe, it never breaks submission.

def _job_marker_key(upload_id: str, period: str) -> str:
    return f"jobs/{upload_id}__{period}.json"


def _analysis_marker_key(period: str) -> str:
    return f"jobs/analysis__{period}.json"


def _existing_live_job(marker_key: str, period: str) -> dict | None:
    """Return an existing NON-terminal job for this idempotency key, else None.

    Reads the durable marker written on the previous submit and queries the job's
    live status. Anything pending/running/completed => return the existing job dict
    (do not spawn a duplicate). Terminally failed (FAILED/CANCELLED/ERROR),
    vanished/not-found, or an unreadable marker => None (a fresh submit is allowed).
    """
    from services import storage

    try:
        marker = storage.download_json(marker_key)
    except Exception:
        return None  # no marker / unreadable => no prior job
    job_id = (marker or {}).get("job_id")
    if not job_id:
        return None
    try:
        status = get_job_status(job_id)
    except Exception:
        # Cannot determine (e.g. the job was deleted / NOT_FOUND) => allow resubmit.
        return None
    st = status.get("status")
    if st == "failed":  # FAILED / CANCELLED / ERROR all map here => allow resubmit
        return None
    logger.info(
        "Idempotent submit: reusing existing job %s (status=%s) for %s — not "
        "creating a duplicate", job_id, st, marker_key,
    )
    return {
        "id": job_id,
        "status": st if st in ("running", "completed") else "pending",
        "period": marker.get("period", period),
        "documentsCount": 0,
        "createdAt": marker.get("createdAt", datetime.now(timezone.utc).isoformat()),
        "nebius_job_name": marker.get("nebius_job_name"),
    }


def _write_job_marker(marker_key: str, job: dict) -> None:
    """Persist the idempotency marker for a freshly-created job (defensive).

    A write failure is logged and swallowed: the job already exists, so losing the
    marker only forfeits dedupe for this key — it must never fail the submit.
    """
    from services import storage

    try:
        storage.put_json(marker_key, {
            "job_id": job.get("id"),
            "nebius_job_name": job.get("nebius_job_name"),
            "period": job.get("period"),
            "createdAt": job.get("createdAt"),
        })
    except Exception:
        logger.warning(
            "Could not write job idempotency marker %s — continuing (dedupe disabled "
            "for this key)", marker_key,
        )


def check_nebius_permissions() -> dict:
    """Smoke-test SA Job-list permissions across every configured project."""
    if JOB_RUNNER_BACKEND != "nebius":
        return {"ok": True, "backend": JOB_RUNNER_BACKEND}
    from nebius.api.nebius.ai.v1 import JobServiceClient, ListJobsRequest

    projects = _project_ladder()
    if not projects:
        return {"ok": False, "error": "no Nebius projects configured"}

    try:
        sdk = _make_sdk()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        svc = JobServiceClient(sdk)
        for project_id in projects:
            try:
                svc.list(ListJobsRequest(parent_id=project_id)).wait()
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"project {project_id}: {exc}",
                    "project": project_id,
                }
        return {"ok": True, "projects": projects}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        sdk.sync_close()


def submit_extraction_job(upload_id: str, period: str) -> dict:
    """Submit a document extraction job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_job(upload_id, period)
    if JOB_RUNNER_BACKEND == "inline":
        return _submit_inline_job(upload_id, period)
    if JOB_RUNNER_BACKEND == "local":
        return _submit_local_job(upload_id, period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_job(upload_id: str, period: str) -> dict:
    from nebius.api.nebius.ai.v1 import JobSpec
    from google.protobuf.duration_pb2 import Duration

    # Idempotency: a prior job for this (upload_id, period) that is still alive is
    # returned as-is — never spawn a duplicate for a retried submit.
    marker_key = _job_marker_key(upload_id, period)
    existing = _existing_live_job(marker_key, period)
    if existing is not None:
        return existing

    # Fetch the registry token once and reuse across ladder attempts (it is a
    # short-lived IAM token; the whole failover completes well within its TTL).
    token = _get_registry_token()

    def build_spec(project_id: str, platform: str, preset: str):
        project = _project_config_for(project_id)
        if not project.subnet_id:
            raise RuntimeError(f"no subnet configured for Nebius project {project_id}")
        return JobSpec(
            image=os.environ["EXTRACTION_JOB_IMAGE"],
            platform=platform,
            preset=preset,
            subnet_id=project.subnet_id,
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
        on_created=lambda job: _write_job_marker(marker_key, job),
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
    # Inline job ids are self-identifying, so their status resolves the same way
    # regardless of the configured backend (robust to a mid-flight backend switch).
    if job_id.startswith("inline-"):
        return _get_inline_job_status(job_id)
    if JOB_RUNNER_BACKEND == "nebius":
        return _get_nebius_job_status(job_id)
    if JOB_RUNNER_BACKEND == "inline":
        return _get_inline_job_status(job_id)
    if JOB_RUNNER_BACKEND == "local":
        return _get_local_job_status(job_id)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def submit_analysis_job(period: str) -> dict:
    """Submit an analysis job and return job metadata."""
    if JOB_RUNNER_BACKEND == "nebius":
        return _submit_nebius_analysis_job(period)
    if JOB_RUNNER_BACKEND == "inline":
        return _submit_inline_analysis_job(period)
    if JOB_RUNNER_BACKEND == "local":
        return _submit_local_analysis_job(period)
    raise NotImplementedError(f"Job runner '{JOB_RUNNER_BACKEND}' not implemented yet")


def _submit_nebius_analysis_job(period: str) -> dict:
    from nebius.api.nebius.ai.v1 import JobSpec
    from google.protobuf.duration_pb2 import Duration

    # Idempotency: a prior analysis job for this period that is still alive is
    # returned as-is — never spawn a duplicate for a retried submit.
    marker_key = _analysis_marker_key(period)
    existing = _existing_live_job(marker_key, period)
    if existing is not None:
        return existing

    job_id_env = uuid.uuid4().hex[:8]
    token = _get_registry_token()

    def build_spec(project_id: str, platform: str, preset: str):
        project = _project_config_for(project_id)
        if not project.subnet_id:
            raise RuntimeError(f"no subnet configured for Nebius project {project_id}")
        return JobSpec(
            image=os.environ["ANALYSIS_JOB_IMAGE"],
            platform=platform,
            preset=preset,
            subnet_id=project.subnet_id,
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
        on_created=lambda job: _write_job_marker(marker_key, job),
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


# ── Inline runner (JOB_RUNNER_BACKEND=inline) ─────────────────────────────────
# Runs the extraction/analysis pipelines IN the backend Endpoint instead of
# submitting Nebius AI Jobs. Rationale: cpu-d3 AI-Jobs quota is a hard 0 tenant-wide
# (verified empirically across eu-west1/eu-north1/uk-south1; the capacity advisor
# covers only VM compute, never Jobs), so a Job is accepted but never provisions.
# Inline execution keeps the pipeline working end-to-end while a quota grant is
# pending. It uses SUBPROCESS isolation (not in-process import) because the two job
# packages have colliding top-level module names (both define `agents` and `models`
# with different contents and no __init__.py); a subprocess gives each its own
# sys.modules and reuses the job entrypoints unchanged (`python main.py`, reading
# UPLOAD_ID/PERIOD from env exactly as the Nebius Job does). Status is tracked in
# Object Storage so the existing poll endpoints work across the async run.

INLINE_EXTRACTION_DIR = os.getenv("INLINE_EXTRACTION_DIR", "/app/jobs/extraction")
INLINE_ANALYSIS_DIR = os.getenv("INLINE_ANALYSIS_DIR", "/app/jobs/analysis")
_INLINE_TIMEOUT_SECS = int(os.getenv("INLINE_JOB_TIMEOUT_SECS", "1800"))


def _inline_status_key(job_id: str) -> str:
    return f"jobs/inline/{job_id}.json"


def _write_inline_status(job_id: str, status: str, period: str, error: str | None = None) -> None:
    from services import storage
    try:
        storage.put_json(_inline_status_key(job_id), {
            "id": job_id, "status": status, "period": period,
            "errorMessage": error,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.warning("Could not write inline status for %s (status=%s)", job_id, status)


def _run_inline(job_id: str, job_dir: str, extra_env: dict, period: str) -> None:
    """Run a job entrypoint as an isolated subprocess; record the outcome to S3."""
    import subprocess
    import sys as _sys
    try:
        env = {**os.environ, **extra_env}
        proc = subprocess.run(
            [_sys.executable, "main.py"], cwd=job_dir, env=env,
            capture_output=True, text=True, timeout=_INLINE_TIMEOUT_SECS,
        )
        if proc.returncode == 0:
            # A clean exit does NOT mean every file was processed: the extraction
            # job catches per-file failures internally and still exits 0. Surface
            # those (otherwise discarded with the captured output) so a silently-
            # dropped upload is visible in the endpoint logs. Scan BOTH streams:
            # the job logs via basicConfig, which writes to STDERR, and the full
            # traceback of the underlying failure lives there too.
            combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if "EXTRACTION FAILED" in combined or "MALFORMED extraction" in combined:
                fail_lines = [ln for ln in combined.splitlines()
                              if "EXTRACTION FAILED" in ln or "MALFORMED extraction" in ln]
                # print() (not just logger) so it is visible regardless of the app's
                # logging config; include a stderr tail carrying the real traceback.
                print(f"[inline {job_id}] COMPLETED WITH EXTRACTION FAILURES: "
                      f"{' | '.join(fail_lines)[-600:]}\n--- stderr tail ---\n"
                      f"{(proc.stderr or '')[-1500:]}", flush=True)
                logger.warning("Inline job %s completed WITH extraction failures", job_id)
            else:
                logger.info("Inline job %s completed (%s)", job_id, job_dir)
            _write_inline_status(job_id, "completed", period)
        else:
            tail = (proc.stderr or proc.stdout or "")[-800:]
            logger.error("Inline job %s failed (rc=%s): %s", job_id, proc.returncode, tail)
            _write_inline_status(job_id, "failed", period, tail or f"exit {proc.returncode}")
    except Exception as exc:
        logger.exception("Inline job %s crashed", job_id)
        _write_inline_status(job_id, "failed", period, str(exc)[-800:])


def _spawn_inline(job_id: str, job_dir: str, extra_env: dict, period: str) -> None:
    _write_inline_status(job_id, "running", period)
    threading.Thread(target=_run_inline, args=(job_id, job_dir, extra_env, period), daemon=True).start()


def _submit_inline_job(upload_id: str, period: str) -> dict:
    job_id = f"inline-ext-{uuid.uuid4().hex[:12]}"
    _spawn_inline(job_id, INLINE_EXTRACTION_DIR, {"UPLOAD_ID": upload_id, "PERIOD": period}, period)
    return {"id": job_id, "status": "running", "period": period,
            "documentsCount": 0, "createdAt": datetime.now(timezone.utc).isoformat(),
            "nebius_job_name": job_id}


def _submit_inline_analysis_job(period: str) -> dict:
    job_id = f"inline-ana-{uuid.uuid4().hex[:12]}"
    _spawn_inline(job_id, INLINE_ANALYSIS_DIR, {"PERIOD": period, "JOB_ID": job_id}, period)
    return {"id": job_id, "status": "running", "period": period,
            "documentsCount": 0, "createdAt": datetime.now(timezone.utc).isoformat()}


def _get_inline_job_status(job_id: str) -> dict:
    from services import storage
    try:
        marker = storage.download_json(_inline_status_key(job_id))
    except Exception:
        # No marker yet (thread not started) => still pending, never an error.
        return {"id": job_id, "status": "pending", "progress": 10,
                "completedAt": None, "errorMessage": None}
    status = (marker or {}).get("status", "pending")
    return {
        "id": job_id,
        "status": status,
        "progress": 100 if status == "completed" else (60 if status == "running" else 10),
        "completedAt": marker.get("updatedAt") if status in ("completed", "failed") else None,
        "errorMessage": marker.get("errorMessage") if status == "failed" else None,
    }
