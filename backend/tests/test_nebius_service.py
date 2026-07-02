"""Unit tests for services/nebius.py.

All Nebius SDK calls are mocked — these tests run without credentials or
network access. JobServiceClient is imported inside functions so it is
patched at its source: nebius.api.nebius.ai.v1.JobServiceClient.
"""
import os
from unittest.mock import MagicMock, patch

import pytest


# ── _get_registry_token ───────────────────────────────────────────────────────

def test_get_registry_token_fallback_to_iam_token(monkeypatch):
    monkeypatch.setenv("NEBIUS_IAM_TOKEN", "my-iam-token")
    monkeypatch.delenv("NEBIUS_SA_KEY_B64", raising=False)
    monkeypatch.delenv("NEBIUS_SA_KEY_ID", raising=False)
    monkeypatch.delenv("NEBIUS_SA_ID", raising=False)

    from services.nebius import _get_registry_token
    assert _get_registry_token() == "my-iam-token"


def test_get_registry_token_returns_empty_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)
    monkeypatch.delenv("NEBIUS_SA_KEY_B64", raising=False)
    monkeypatch.delenv("NEBIUS_SA_KEY_ID", raising=False)
    monkeypatch.delenv("NEBIUS_SA_ID", raising=False)

    from services.nebius import _get_registry_token
    assert _get_registry_token() == ""


def _set_sa_env(monkeypatch):
    """Populate the three SA env vars with syntactically-valid placeholders."""
    import base64
    fake_pem = b"-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
    monkeypatch.setenv("NEBIUS_SA_KEY_B64", base64.b64encode(fake_pem).decode())
    monkeypatch.setenv("NEBIUS_SA_KEY_ID", "key-id-001")
    monkeypatch.setenv("NEBIUS_SA_ID", "sa-001")


def test_get_registry_token_uses_sa_bearer_not_http(monkeypatch):
    """With SA vars set, the token is minted via the pysdk SA bearer
    (`_make_sdk().get_token_sync().token`) — the SAME path JobService uses — NOT
    via an HTTP POST to any OAuth endpoint. The old code POSTed a JWT to the
    wrong endpoint and silently fell back; this asserts the SA path is taken."""
    _set_sa_env(monkeypatch)
    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)

    fake_token = MagicMock()
    fake_token.token = "sa-generated-token"
    fake_sdk = MagicMock()
    fake_sdk.get_token_sync.return_value = fake_token

    with patch("services.nebius._make_sdk", return_value=fake_sdk):
        from services.nebius import _get_registry_token
        token = _get_registry_token()

    assert token == "sa-generated-token"
    fake_sdk.get_token_sync.assert_called_once()   # SA bearer path was used
    fake_sdk.sync_close.assert_called_once()        # SDK is always closed


def test_get_registry_token_raises_when_sa_mint_fails(monkeypatch):
    """The behavioural change: with SA vars present, a mint failure RAISES and
    does NOT fall back to a (possibly stale) NEBIUS_IAM_TOKEN. The old code
    swallowed the failure and returned the ephemeral session token, masking
    broken registry auth behind a ~12h fuse."""
    _set_sa_env(monkeypatch)
    monkeypatch.setenv("NEBIUS_IAM_TOKEN", "stale-fallback-token")

    fake_sdk = MagicMock()
    fake_sdk.get_token_sync.side_effect = RuntimeError("mint boom")

    with patch("services.nebius._make_sdk", return_value=fake_sdk):
        from services.nebius import _get_registry_token
        with pytest.raises(RuntimeError, match="mint boom"):
            _get_registry_token()

    fake_sdk.sync_close.assert_called_once()        # SDK still closed on failure


def test_get_registry_token_raises_on_empty_sa_token(monkeypatch):
    """An empty minted token is refused loudly, never returned — submitting a job
    with no registry auth would fail opaquely at provisioning instead."""
    _set_sa_env(monkeypatch)
    monkeypatch.setenv("NEBIUS_IAM_TOKEN", "stale-fallback-token")

    fake_token = MagicMock()
    fake_token.token = ""
    fake_sdk = MagicMock()
    fake_sdk.get_token_sync.return_value = fake_token

    with patch("services.nebius._make_sdk", return_value=fake_sdk):
        from services.nebius import _get_registry_token
        with pytest.raises(RuntimeError, match="empty token"):
            _get_registry_token()


# ── REAL-SDK token-bearer contract ────────────────────────────────────────────
# The mocks above assert we CALL get_token_sync, but a mock can never catch the
# pinned SDK renaming/removing that method — exactly the proto/API-drift class of
# bug that put the registry_credentials list form into prod. This exercises the
# REAL pinned nebius==0.3.76 surface so a future SDK that drops the token-bearer
# API fails HERE instead of at the first live job submission.

def test_registry_token_bearer_api_exists_on_real_sdk():
    pytest.importorskip("nebius")
    from nebius.sdk import SDK

    # get_token_sync(timeout, options=None) -> Token; Token.token is the string.
    assert hasattr(SDK, "get_token_sync")
    assert callable(SDK.get_token_sync)
    from nebius.aio.token.token import Token
    assert isinstance(Token.__dict__["token"], property)


# ── _JOB_STATE_MAP ────────────────────────────────────────────────────────────

def test_job_state_map_has_terminal_completed():
    from services.nebius import _JOB_STATE_MAP
    assert "completed" in _JOB_STATE_MAP.values()


def test_job_state_map_has_terminal_failed():
    from services.nebius import _JOB_STATE_MAP
    assert "failed" in _JOB_STATE_MAP.values()


def test_job_state_map_has_running():
    from services.nebius import _JOB_STATE_MAP
    assert "running" in _JOB_STATE_MAP.values()


def test_job_state_map_minimum_entries():
    from services.nebius import _JOB_STATE_MAP
    assert len(_JOB_STATE_MAP) >= 4


# ── JobSpec mock helpers ──────────────────────────────────────────────────────

def _make_jobspec_class():
    """Return a mock JobSpec class that records constructor kwargs."""
    class FakeRegistryCredentials:
        def __init__(self, username, password):
            self.username = username
            self.password = password

    class FakeDiskSpec:
        def __init__(self, type, size_bytes):
            self.type = type
            self.size_bytes = size_bytes

    class FakeEnvVar:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class FakeJobSpec:
        RegistryCredentials = FakeRegistryCredentials
        DiskSpec = FakeDiskSpec
        EnvironmentVariable = FakeEnvVar

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return FakeJobSpec


def _make_status(state: int = 3, instances: int = 1, started: bool = True, message: str = ""):
    """Build a fake JobStatus with the real wrapper's field surface.

    Mirrors the installed pysdk shape: `.state` (int), `.instances` (list),
    `.check_presence('started_at')` (bool), `.state_details.message` (str).
    Default = RUNNING with one instance (provisioned).
    """
    status = MagicMock()
    status.state = state
    status.instances = [MagicMock() for _ in range(instances)]
    status.check_presence.side_effect = lambda name: started if name == "started_at" else False
    status.state_details = MagicMock()
    status.state_details.message = message
    return status


def _make_mock_job(job_id: str = "job-nebius-001", status=None):
    meta = MagicMock()
    meta.id = job_id
    job = MagicMock()
    job.metadata = meta
    # create(...).wait() returns an Operation; the created job id is on
    # Operation.resource_id (Operation has no .metadata).
    job.resource_id = job_id
    # get(...).wait() returns a Job whose .status the provisioning probe reads.
    job.status = status if status is not None else _make_status()
    return job


def _wrap(job):
    """Wrap a job in a MagicMock whose .wait() returns it (SDK operation shape)."""
    result = MagicMock()
    result.wait.return_value = job
    return result


def _make_create_result(job_id: str = "job-nebius-001"):
    return _wrap(_make_mock_job(job_id))


def _make_sdk_and_service(job_id: str = "job-nebius-001"):
    """SDK + service where create() succeeds and the job provisions (RUNNING)."""
    service = MagicMock()
    service.create.return_value = _make_create_result(job_id)
    # _await_provisioning calls service.get(...).wait() -> RUNNING job by default.
    service.get.return_value = _wrap(_make_mock_job(job_id))
    sdk = MagicMock()
    sdk.sync_close = MagicMock()
    return sdk, service


# ── _submit_nebius_job (extraction) ───────────────────────────────────────────

def _patch_nebius_imports(sdk, service, FakeJobSpec):
    """Context manager stack for patching all nebius SDK imports used in _submit_nebius_job."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("services.nebius._make_sdk", return_value=sdk))
    stack.enter_context(patch("services.nebius._delete_nebius_error_jobs"))
    stack.enter_context(patch("services.nebius._get_registry_token", return_value="test-token"))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.JobServiceClient", return_value=service))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.CreateJobRequest", side_effect=lambda **kw: MagicMock(**kw)))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.JobSpec", FakeJobSpec))
    stack.enter_context(patch("nebius.api.nebius.common.v1.ResourceMetadata", side_effect=lambda **kw: MagicMock(**kw)))
    stack.enter_context(patch("google.protobuf.duration_pb2.Duration", side_effect=lambda **kw: MagicMock(**kw)))
    return stack


def test_submit_extraction_job_returns_dict(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("EXTRACTION_JOB_IMAGE", "cr.test/archon-extraction:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service("job-001")
    FakeJobSpec = _make_jobspec_class()

    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        result = _submit_nebius_job("upload-abc", "2025-01")

    assert result["id"] == "job-001"
    assert result["period"] == "2025-01"
    assert result["status"] == "pending"
    assert "createdAt" in result


def test_submit_extraction_job_closes_sdk_on_success(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("EXTRACTION_JOB_IMAGE", "cr.test/archon-extraction:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service()
    FakeJobSpec = _make_jobspec_class()

    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        _submit_nebius_job("upload-abc", "2025-02")

    sdk.sync_close.assert_called_once()


def test_submit_extraction_job_closes_sdk_on_error(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("EXTRACTION_JOB_IMAGE", "cr.test/archon-extraction:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk = MagicMock()
    sdk.sync_close = MagicMock()
    service = MagicMock()
    service.create.side_effect = RuntimeError("SDK error")
    FakeJobSpec = _make_jobspec_class()

    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        with pytest.raises(RuntimeError):
            _submit_nebius_job("upload-abc", "2025-03")

    sdk.sync_close.assert_called_once()


def test_submit_extraction_job_passes_registry_credentials(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("EXTRACTION_JOB_IMAGE", "cr.test/archon-extraction:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service()
    FakeJobSpec = _make_jobspec_class()

    captured_specs = []

    class CapturingJobSpec(FakeJobSpec):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured_specs.append(self)

    with _patch_nebius_imports(sdk, service, CapturingJobSpec):
        from services.nebius import _submit_nebius_job
        _submit_nebius_job("upload-abc", "2025-01")

    assert len(captured_specs) == 1
    spec = captured_specs[0]
    assert hasattr(spec, "registry_credentials")
    # registry_credentials is a SINGULAR RegistryCredentials message in the
    # Nebius proto (JobSpec.registry_credentials = 10), not a repeated field.
    # Passing a list made the SDK setter call .extend() on a non-repeated
    # wrapper -> AttributeError -> 500 on POST /api/jobs.
    creds = spec.registry_credentials
    assert creds is not None
    assert creds.username == "iam"
    assert creds.password == "test-token"


# ── _submit_nebius_analysis_job ───────────────────────────────────────────────

def _patch_analysis_imports(sdk, service, FakeJobSpec):
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("services.nebius._make_sdk", return_value=sdk))
    stack.enter_context(patch("services.nebius._delete_nebius_error_jobs"))
    stack.enter_context(patch("services.nebius._get_registry_token", return_value="analysis-token"))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.JobServiceClient", return_value=service))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.CreateJobRequest", side_effect=lambda **kw: MagicMock(**kw)))
    stack.enter_context(patch("nebius.api.nebius.ai.v1.JobSpec", FakeJobSpec))
    stack.enter_context(patch("nebius.api.nebius.common.v1.ResourceMetadata", side_effect=lambda **kw: MagicMock(**kw)))
    stack.enter_context(patch("google.protobuf.duration_pb2.Duration", side_effect=lambda **kw: MagicMock(**kw)))
    return stack


def test_submit_analysis_job_returns_dict(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("ANALYSIS_JOB_IMAGE", "cr.test/archon-analysis:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service("analysis-001")
    FakeJobSpec = _make_jobspec_class()

    with _patch_analysis_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_analysis_job
        result = _submit_nebius_analysis_job("2025-06")

    assert result["id"] == "analysis-001"
    assert result["period"] == "2025-06"
    assert result["status"] == "pending"
    assert "createdAt" in result


def test_submit_analysis_job_passes_registry_credentials(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("ANALYSIS_JOB_IMAGE", "cr.test/archon-analysis:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service()
    FakeJobSpec = _make_jobspec_class()

    captured_specs = []

    class CapturingJobSpec(FakeJobSpec):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured_specs.append(self)

    with _patch_analysis_imports(sdk, service, CapturingJobSpec):
        from services.nebius import _submit_nebius_analysis_job
        _submit_nebius_analysis_job("2025-06")

    assert len(captured_specs) == 1
    creds = captured_specs[0].registry_credentials
    assert creds is not None
    assert creds.username == "iam"
    assert creds.password == "analysis-token"


def test_submit_analysis_job_closes_sdk_on_error(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("ANALYSIS_JOB_IMAGE", "cr.test/archon-analysis:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk = MagicMock()
    sdk.sync_close = MagicMock()
    service = MagicMock()
    service.create.side_effect = RuntimeError("analysis error")
    FakeJobSpec = _make_jobspec_class()

    with _patch_analysis_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_analysis_job
        with pytest.raises(RuntimeError):
            _submit_nebius_analysis_job("2025-06")

    sdk.sync_close.assert_called_once()


# ── REAL-SDK proto contract (integration-level) ───────────────────────────────
# The mock-based tests above assert the *shape* we pass, but a FakeJobSpec can
# never catch an SDK proto-contract change — which is exactly how the list form
# reached production (CI green, prod 500). This test exercises the REAL Nebius
# SDK setter, so a future SDK that changes the registry_credentials arity fails
# here instead of in production.

def test_registry_credentials_singular_against_real_sdk():
    """JobSpec.registry_credentials is singular; passing a list raises in-SDK."""
    JobSpec = pytest.importorskip("nebius.api.nebius.ai.v1").JobSpec

    rc = JobSpec.RegistryCredentials(username="iam", password="x")

    # The fix: a singular message is accepted and round-trips.
    spec = JobSpec(registry_credentials=rc)
    assert spec.registry_credentials.username == "iam"

    # The old bug: a one-element list makes the singular setter call .extend()
    # on a non-repeated wrapper -> AttributeError -> the prod 500 on /api/jobs.
    with pytest.raises(AttributeError):
        JobSpec(registry_credentials=[rc])


# ── Preset ladder parsing ─────────────────────────────────────────────────────

def test_parse_ladder_env_empty_returns_empty(monkeypatch):
    monkeypatch.delenv("JOB_PRESET_LADDER", raising=False)
    from services.nebius import _parse_ladder_env
    assert _parse_ladder_env() == []


def test_parse_ladder_env_valid(monkeypatch):
    monkeypatch.setenv("JOB_PRESET_LADDER", "cpu-d3:4vcpu-16gb, cpu-d3:8vcpu-32gb")
    from services.nebius import _parse_ladder_env
    assert _parse_ladder_env() == [("cpu-d3", "4vcpu-16gb"), ("cpu-d3", "8vcpu-32gb")]


def test_parse_ladder_env_skips_malformed(monkeypatch):
    # 'garbage' has no colon; ':x' and 'y:' are empty-sided → all skipped.
    monkeypatch.setenv("JOB_PRESET_LADDER", "garbage,cpu-d3:16vcpu-64gb,:x,y:,")
    from services.nebius import _parse_ladder_env
    assert _parse_ladder_env() == [("cpu-d3", "16vcpu-64gb")]


def test_preset_ladder_default_puts_live_first_then_fallback(monkeypatch):
    monkeypatch.delenv("JOB_PRESET_LADDER", raising=False)
    from services.nebius import _preset_ladder, _DEFAULT_FALLBACK_LADDER
    ladder = _preset_ladder("cpu-d3", "4vcpu-16gb")
    assert ladder[0] == ("cpu-d3", "4vcpu-16gb")
    for entry in _DEFAULT_FALLBACK_LADDER:
        assert entry in ladder


def test_preset_ladder_env_overrides_default(monkeypatch):
    monkeypatch.setenv("JOB_PRESET_LADDER", "cpu-d3:8vcpu-32gb,cpu-d3:16vcpu-64gb")
    from services.nebius import _preset_ladder
    assert _preset_ladder("cpu-d3", "4vcpu-16gb") == [
        ("cpu-d3", "8vcpu-32gb"),
        ("cpu-d3", "16vcpu-64gb"),
    ]


def test_preset_ladder_dedups_preserving_order(monkeypatch):
    # Live rung equals the single fallback → must not appear twice.
    monkeypatch.delenv("JOB_PRESET_LADDER", raising=False)
    from services.nebius import _preset_ladder
    ladder = _preset_ladder("cpu-d3", "8vcpu-32gb")
    assert ladder.count(("cpu-d3", "8vcpu-32gb")) == 1


def test_is_provisioning_error_matches_quota_and_precondition():
    from services.nebius import _is_provisioning_error
    assert _is_provisioning_error(RuntimeError("FAILED_PRECONDITION: no capacity"))
    assert _is_provisioning_error(RuntimeError("RESOURCE_EXHAUSTED: quota exceeded"))
    assert not _is_provisioning_error(RuntimeError("invalid image reference"))


# ── Failover behaviour (the critical signal) ──────────────────────────────────

def _failover_env(monkeypatch, image_key="EXTRACTION_JOB_IMAGE"):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv(image_key, "cr.test/img:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")
    monkeypatch.setenv("JOB_PROVISION_PROBE_SECS", "0")
    monkeypatch.setenv("JOB_PROVISION_POLL_SECS", "0")
    # Two-rung ladder so a single fallover is observable.
    monkeypatch.setenv("JOB_PRESET_LADDER", "cpu-d3:4vcpu-16gb,cpu-d3:8vcpu-32gb")


def test_failover_when_first_preset_never_provisions(monkeypatch):
    """Rung 1 terminal-fails with 0 instances → rung 2 is tried and succeeds."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    # create() returns job-1 then job-2 on successive attempts.
    service.create.side_effect = [_make_create_result("job-1"), _make_create_result("job-2")]
    # get(): job-1 FAILED with 0 instances (never provisioned); job-2 RUNNING.
    never = _make_mock_job("job-1", _make_status(state=7, instances=0, started=False))
    running = _make_mock_job("job-2", _make_status(state=3, instances=1, started=True))
    service.get.side_effect = [_wrap(never), _wrap(running)]
    service.delete.return_value = _wrap(MagicMock())

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        result = _submit_nebius_job("upload-abc", "2025-01")

    assert result["id"] == "job-2"          # succeeded on rung 2
    assert service.create.call_count == 2   # both rungs tried
    service.delete.assert_called_once()     # rung-1 scaffolding cleaned up


def test_no_failover_when_job_ran_then_failed(monkeypatch):
    """Reached compute then failed = application bug → fail fast, NO failover."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = [_make_create_result("job-1"), _make_create_result("job-2")]
    # job-1 FAILED but started_at set + 1 instance → compute existed → app failure.
    app_fail = _make_mock_job("job-1", _make_status(state=7, instances=1, started=True, message="boom"))
    service.get.side_effect = [_wrap(app_fail)]

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        with pytest.raises(RuntimeError) as exc_info:
            _submit_nebius_job("upload-abc", "2025-01")

    assert "after provisioning" in str(exc_info.value)
    assert service.create.call_count == 1   # did NOT try rung 2
    service.delete.assert_not_called()


def test_all_presets_never_provision_raises_capacity_error(monkeypatch):
    """Every rung never provisions → ComputeCapacityUnavailable (→ 503), bounded."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = [_make_create_result("job-1"), _make_create_result("job-2")]
    never1 = _make_mock_job("job-1", _make_status(state=9, instances=0, started=False))  # ERROR
    never2 = _make_mock_job("job-2", _make_status(state=7, instances=0, started=False))  # FAILED
    service.get.side_effect = [_wrap(never1), _wrap(never2)]
    service.delete.return_value = _wrap(MagicMock())

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job, ComputeCapacityUnavailable
        with pytest.raises(ComputeCapacityUnavailable) as exc_info:
            _submit_nebius_job("upload-abc", "2025-01")

    msg = str(exc_info.value)
    assert "capacity" in msg.lower()
    assert service.create.call_count == 2   # bounded: exactly one attempt per rung
    assert service.delete.call_count == 2   # both scaffolds cleaned up


def test_submission_provisioning_error_fails_over(monkeypatch):
    """A FAILED_PRECONDITION at create() time fails over to the next preset."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    running = _make_mock_job("job-2", _make_status(state=3, instances=1, started=True))
    service.create.side_effect = [
        RuntimeError("FAILED_PRECONDITION: preset has no quota"),
        _make_create_result("job-2"),
    ]
    service.get.side_effect = [_wrap(running)]

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        result = _submit_nebius_job("upload-abc", "2025-01")

    assert result["id"] == "job-2"
    assert service.create.call_count == 2


def test_non_provisioning_submission_error_is_reraised(monkeypatch):
    """A genuine (non-capacity) create() error is raised, NOT failed over."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = RuntimeError("invalid image reference")

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        with pytest.raises(RuntimeError, match="invalid image"):
            _submit_nebius_job("upload-abc", "2025-01")

    assert service.create.call_count == 1   # no failover on a real error


def test_analysis_job_fails_over_too(monkeypatch):
    """The shared helper applies to analysis jobs as well (DRY)."""
    _failover_env(monkeypatch, image_key="ANALYSIS_JOB_IMAGE")

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = [_make_create_result("an-1"), _make_create_result("an-2")]
    never = _make_mock_job("an-1", _make_status(state=8, instances=0, started=False))  # CANCELLED
    running = _make_mock_job("an-2", _make_status(state=3, instances=1, started=True))
    service.get.side_effect = [_wrap(never), _wrap(running)]
    service.delete.return_value = _wrap(MagicMock())

    FakeJobSpec = _make_jobspec_class()
    with _patch_analysis_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_analysis_job
        result = _submit_nebius_analysis_job("2025-06")

    assert result["id"] == "an-2"
    assert service.create.call_count == 2


def test_accept_then_stall_provisioning_triggers_failover(monkeypatch):
    """The #81 gap: a job accepted but stuck in PROVISIONING with 0 instances past
    the probe deadline (the zero-capacity accept-then-stall signature) must be
    classified _NEVER_PROVISIONED → deleted → failed over to the next rung.

    Before the fix this returned _PROVISIONED (pending) and the job stalled forever.
    The stall state is PROVISIONING (1) with 0 instances and no started_at — it is
    NOT a terminal-failure state, so it reaches the deadline branch, unlike the
    terminal-failure failover tests above.
    """
    _failover_env(monkeypatch)  # JOB_PROVISION_PROBE_SECS=0 → deadline hits at once

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = [_make_create_result("job-1"), _make_create_result("job-2")]
    # job-1: PROVISIONING (1), 0 instances, never started → accept-then-stall.
    stalled = _make_mock_job("job-1", _make_status(state=1, instances=0, started=False))
    running = _make_mock_job("job-2", _make_status(state=3, instances=1, started=True))
    service.get.side_effect = [_wrap(stalled), _wrap(running)]
    service.delete.return_value = _wrap(MagicMock())

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        result = _submit_nebius_job("upload-abc", "2025-01")

    assert result["id"] == "job-2"          # failed over to rung 2
    assert service.create.call_count == 2   # both rungs tried
    service.delete.assert_called_once()     # stalled rung-1 scaffolding deleted


def test_job_vanished_during_probe_triggers_failover(monkeypatch):
    """GetJob raising (job torn itself down) counts as never-provisioned."""
    _failover_env(monkeypatch)

    sdk, service = _make_sdk_and_service()
    service.create.side_effect = [_make_create_result("job-1"), _make_create_result("job-2")]
    running = _make_mock_job("job-2", _make_status(state=3, instances=1, started=True))
    service.get.side_effect = [RuntimeError("NOT_FOUND: job deleted"), _wrap(running)]
    service.delete.return_value = _wrap(MagicMock())

    FakeJobSpec = _make_jobspec_class()
    with _patch_nebius_imports(sdk, service, FakeJobSpec):
        from services.nebius import _submit_nebius_job
        result = _submit_nebius_job("upload-abc", "2025-01")

    assert result["id"] == "job-2"
    assert service.create.call_count == 2


# ── REAL-SDK JobStatus shape contract ─────────────────────────────────────────
# The failover logic reads specific JobStatus fields. A FakeJobSpec/mock can never
# catch an SDK proto-contract change to these — exactly how the registry_credentials
# arity bug reached prod. This exercises the REAL pysdk so drift on the fields the
# failover relies on fails HERE instead of as a prod 500 / silent stall.

def test_jobstatus_shape_against_real_sdk():
    v1 = pytest.importorskip("nebius.api.nebius.ai.v1")
    JobStatus = v1.JobStatus

    status = JobStatus()
    # Fields the probe reads:
    assert isinstance(status.state, int)          # .state
    assert len(status.instances) == 0             # .instances (repeated)
    # Field-presence API is check_presence(), NOT HasField() (which the wrapper
    # does not expose — depending on HasField here would be a prod bug).
    assert status.check_presence("started_at") is False
    assert not hasattr(status, "HasField")
    assert status.state_details.message == ""     # .state_details.message

    # The state machine values the classifier keys on must exist and be distinct.
    S = JobStatus.State
    for name in ("PROVISIONING", "STARTING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "ERROR"):
        assert hasattr(S, name)
    assert int(S.RUNNING) == 3
    assert {int(S.FAILED), int(S.CANCELLED), int(S.ERROR)} == {7, 8, 9}


# ── submit_extraction_job routing ─────────────────────────────────────────────

def test_submit_extraction_job_routes_to_nebius_backend(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("EXTRACTION_JOB_IMAGE", "cr.test/archon-extraction:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service("routed-001")
    FakeJobSpec = _make_jobspec_class()

    import services.nebius as svc
    original = svc.JOB_RUNNER_BACKEND
    svc.JOB_RUNNER_BACKEND = "nebius"
    try:
        with _patch_nebius_imports(sdk, service, FakeJobSpec):
            result = svc.submit_extraction_job("upload-xyz", "2025-01")
    finally:
        svc.JOB_RUNNER_BACKEND = original

    assert result["id"] == "routed-001"


def test_submit_analysis_job_routes_to_nebius_backend(monkeypatch):
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-test")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-test")
    monkeypatch.setenv("ANALYSIS_JOB_IMAGE", "cr.test/archon-analysis:latest")
    monkeypatch.setenv("NEBIUS_INFERENCE_BASE_URL", "https://api.test")
    monkeypatch.setenv("NEBIUS_INFERENCE_API_KEY", "key")

    sdk, service = _make_sdk_and_service("routed-analysis-001")
    FakeJobSpec = _make_jobspec_class()

    import services.nebius as svc
    original = svc.JOB_RUNNER_BACKEND
    svc.JOB_RUNNER_BACKEND = "nebius"
    try:
        with _patch_analysis_imports(sdk, service, FakeJobSpec):
            result = svc.submit_analysis_job("2025-06")
    finally:
        svc.JOB_RUNNER_BACKEND = original

    assert result["id"] == "routed-analysis-001"


def test_submit_extraction_job_raises_for_unknown_backend():
    import services.nebius as svc
    original = svc.JOB_RUNNER_BACKEND
    svc.JOB_RUNNER_BACKEND = "unknown-cloud"
    try:
        with pytest.raises(NotImplementedError):
            svc.submit_extraction_job("upload-x", "2025-01")
    finally:
        svc.JOB_RUNNER_BACKEND = original


# ── check_nebius_permissions ──────────────────────────────────────────────────

def test_check_nebius_permissions_returns_ok_for_non_nebius_backend():
    import services.nebius as svc
    original = svc.JOB_RUNNER_BACKEND
    svc.JOB_RUNNER_BACKEND = "local"
    try:
        result = svc.check_nebius_permissions()
    finally:
        svc.JOB_RUNNER_BACKEND = original

    assert result.get("ok") is True
    assert result.get("backend") == "local"


def test_check_nebius_permissions_returns_dict_on_sdk_error():
    import services.nebius as svc
    original = svc.JOB_RUNNER_BACKEND
    svc.JOB_RUNNER_BACKEND = "nebius"
    try:
        with patch("services.nebius._make_sdk", side_effect=RuntimeError("no creds")):
            result = svc.check_nebius_permissions()
    finally:
        svc.JOB_RUNNER_BACKEND = original

    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert "error" in result


def test_get_nebius_job_status_uses_pysdk_wrapper_shape(monkeypatch):
    """Regression: the pysdk JobStatus is a wrapper, not a raw protobuf.
    Status must be read via check_presence()/datetime, not HasField()/ToDatetime().
    This path was previously untested (test_jobs uses the local runner) and shipped
    an AttributeError to prod on every /api/jobs/<id> poll."""
    import services.nebius as svc
    from datetime import datetime, timezone

    status = MagicMock()
    status.state = 6  # COMPLETED
    status.check_presence.return_value = True
    status.finished_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    status.state_details.message = ""
    job = MagicMock()
    job.status = status

    get_result = MagicMock()
    get_result.wait.return_value = job
    service = MagicMock()
    service.get.return_value = get_result
    sdk = MagicMock()

    with patch("services.nebius._make_sdk", return_value=sdk), \
         patch("nebius.api.nebius.ai.v1.JobServiceClient", return_value=service), \
         patch("nebius.api.nebius.ai.v1.GetJobRequest", side_effect=lambda **kw: MagicMock(**kw)):
        result = svc._get_nebius_job_status("aijob-xyz")

    status.check_presence.assert_called_with("finished_at")
    assert result["status"] == "completed"
    assert result["completedAt"] == "2026-01-02T03:04:05+00:00"
    assert result["progress"] == 100
