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


def test_get_registry_token_uses_sa_credentials(monkeypatch):
    import base64
    fake_pem = b"-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
    monkeypatch.setenv("NEBIUS_SA_KEY_B64", base64.b64encode(fake_pem).decode())
    monkeypatch.setenv("NEBIUS_SA_KEY_ID", "key-id-001")
    monkeypatch.setenv("NEBIUS_SA_ID", "sa-001")
    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"access_token": "sa-generated-token"}

    with patch("requests.post", return_value=mock_resp), \
         patch("jwt.encode", return_value="signed.jwt.token"):
        from services.nebius import _get_registry_token
        token = _get_registry_token()

    assert token == "sa-generated-token"


def test_get_registry_token_sa_fallback_on_jwt_error(monkeypatch):
    import base64
    fake_pem = b"-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
    monkeypatch.setenv("NEBIUS_SA_KEY_B64", base64.b64encode(fake_pem).decode())
    monkeypatch.setenv("NEBIUS_SA_KEY_ID", "key-id-001")
    monkeypatch.setenv("NEBIUS_SA_ID", "sa-001")
    monkeypatch.setenv("NEBIUS_IAM_TOKEN", "fallback-token")

    with patch("jwt.encode", side_effect=Exception("JWT error")):
        from services.nebius import _get_registry_token
        token = _get_registry_token()

    assert token == "fallback-token"


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


def _make_mock_job(job_id: str = "job-nebius-001"):
    meta = MagicMock()
    meta.id = job_id
    job = MagicMock()
    job.metadata = meta
    # service.create(...).wait() returns an Operation; the created job id is on
    # Operation.resource_id (Operation has no .metadata).
    job.resource_id = job_id
    return job


def _make_create_result(job_id: str = "job-nebius-001"):
    mock_job = _make_mock_job(job_id)
    result = MagicMock()
    result.wait.return_value = mock_job
    return result


def _make_sdk_and_service(job_id: str = "job-nebius-001"):
    create_result = _make_create_result(job_id)
    service = MagicMock()
    service.create.return_value = create_result
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
