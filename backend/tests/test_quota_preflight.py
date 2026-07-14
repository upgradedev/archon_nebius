"""Unit tests for the AI-Jobs quota pre-flight (backend/services/nebius.py).

The pre-flight turns a would-be 30-minute PROVISION-then-FAIL (when cpu-d3
AI-Jobs quota is a hard 0) into an instant, named HTTP 503 — but only when
explicitly enabled (JOB_QUOTA_PREFLIGHT) and only on a *confirmed* zero. It is
fail-open: any uncertainty must let the submission proceed exactly as before.

All tests mock the SDK; no real Nebius credentials are required."""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from services import nebius


def _item(region, name="", service="", desc="", limit=0):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(region=region, limit=limit),
        status=SimpleNamespace(service=service, description=desc),
    )


def _patched_client(items):
    """Patch _make_sdk + QuotaAllowanceServiceClient so .list().wait().items == items."""
    resp = SimpleNamespace(items=items)
    client = MagicMock()
    client.list.return_value.wait.return_value = resp
    return (
        patch("services.nebius._make_sdk", return_value=MagicMock()),
        patch("nebius.api.nebius.quotas.v1.QuotaAllowanceServiceClient", return_value=client),
    )


pytest.importorskip("nebius.api.nebius.quotas.v1")


# ── _jobs_quota_state ─────────────────────────────────────────────────────────

def test_quota_state_zero_when_matching_limit_zero():
    items = [_item("eu-west1", name="compute.jobs.cpu-d3", limit=0)]
    p_sdk, p_cli = _patched_client(items)
    with p_sdk, p_cli:
        state, limit = nebius._jobs_quota_state("proj", "eu-west1", "cpu-d3")
    assert state == "zero"
    assert limit == 0


def test_quota_state_available_when_limit_positive():
    items = [_item("eu-west1", service="compute-jobs cpu-d3", limit=16)]
    p_sdk, p_cli = _patched_client(items)
    with p_sdk, p_cli:
        state, limit = nebius._jobs_quota_state("proj", "eu-west1", "cpu-d3")
    assert state == "available"
    assert limit == 16


def test_quota_state_unknown_for_other_region():
    items = [_item("eu-north1", name="compute.jobs.cpu-d3", limit=0)]
    p_sdk, p_cli = _patched_client(items)
    with p_sdk, p_cli:
        state, _ = nebius._jobs_quota_state("proj", "eu-west1", "cpu-d3")
    assert state == "unknown"


def test_quota_state_fail_open_on_exception():
    with patch("services.nebius._make_sdk", side_effect=RuntimeError("no creds")):
        state, _ = nebius._jobs_quota_state("proj", "eu-west1", "cpu-d3")
    assert state == "unknown"


# ── _preflight_jobs_quota (gate + raise) ──────────────────────────────────────

def test_preflight_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("JOB_QUOTA_PREFLIGHT", raising=False)
    # If disabled, it must not even look at quota — _jobs_quota_state untouched.
    with patch("services.nebius._jobs_quota_state", side_effect=AssertionError("should not run")):
        nebius._preflight_jobs_quota("proj", "cpu-d3")  # no raise, no call


def test_preflight_raises_on_confirmed_zero(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    with patch("services.nebius._jobs_quota_state", return_value=("zero", 0)):
        with pytest.raises(nebius.NoJobsQuota) as ei:
            nebius._preflight_jobs_quota("proj", "cpu-d3")
    # Mapped to the same 503 family, and names the region.
    assert isinstance(ei.value, nebius.ComputeCapacityUnavailable)
    assert "cpu-d3" in str(ei.value)


def test_preflight_proceeds_when_available(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    with patch("services.nebius._jobs_quota_state", return_value=("available", 16)):
        nebius._preflight_jobs_quota("proj", "cpu-d3")  # no raise


def test_preflight_proceeds_when_unknown_fail_open(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    with patch("services.nebius._jobs_quota_state", return_value=("unknown", None)):
        nebius._preflight_jobs_quota("proj", "cpu-d3")  # no raise


# ── _route_projects_by_quota (active selector) ────────────────────────────────

_PRESETS = [("cpu-d3", "4vcpu-16gb"), ("cpu-d3", "8vcpu-32gb")]


def test_routing_noop_and_no_lookups_when_disabled(monkeypatch):
    monkeypatch.delenv("JOB_QUOTA_PREFLIGHT", raising=False)
    # Disabled => projects returned verbatim, verdict empty, quota API never touched.
    with patch("services.nebius._jobs_quota_state", side_effect=AssertionError("should not run")):
        ordered, verdict = nebius._route_projects_by_quota(["p1", "p2"], _PRESETS, "eu-west1")
    assert ordered == ["p1", "p2"]
    assert verdict == {}


def test_routing_drops_confirmed_zero_project(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")

    def fake(project, region, platform):
        return ("zero", 0) if project == "zero-proj" else ("available", 16)

    with patch("services.nebius._jobs_quota_state", side_effect=fake):
        ordered, verdict = nebius._route_projects_by_quota(["zero-proj", "ok-proj"], _PRESETS, "eu-west1")
    assert ordered == ["ok-proj"]  # zero project dropped up front
    assert verdict[("zero-proj", "cpu-d3")] == "zero"


def test_routing_orders_available_before_unknown(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    states = {"a": ("unknown", None), "b": ("available", 8)}

    with patch("services.nebius._jobs_quota_state", side_effect=lambda p, r, pl: states[p]):
        ordered, _ = nebius._route_projects_by_quota(["a", "b"], _PRESETS, "eu-west1")
    assert ordered == ["b", "a"]  # available-first


def test_routing_keeps_unknown_fail_open(monkeypatch):
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    with patch("services.nebius._jobs_quota_state", return_value=("unknown", None)):
        ordered, verdict = nebius._route_projects_by_quota(["p1"], _PRESETS, "eu-west1")
    assert ordered == ["p1"]  # never dropped on uncertainty
    assert verdict[("p1", "cpu-d3")] == "unknown"


def test_submit_raises_nojobsquota_when_every_project_zero(monkeypatch):
    """The whole point of the selector: a confirmed all-zero tenant yields an
    INSTANT named 503, never a 30-minute provision-then-FAIL — and no job is
    ever created."""
    monkeypatch.setenv("JOB_QUOTA_PREFLIGHT", "1")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "only-proj")
    monkeypatch.delenv("NEBIUS_PROJECT_ID_LADDER", raising=False)
    monkeypatch.delenv("JOB_PRESET_LADDER", raising=False)

    created = MagicMock()
    with patch("services.nebius._jobs_quota_state", return_value=("zero", 0)), \
         patch("services.nebius._delete_nebius_error_jobs") as sweep:
        with pytest.raises(nebius.NoJobsQuota):
            nebius._submit_job_with_failover(
                name_prefix="archon-extract",
                period="2026-03",
                default_platform="cpu-d3",
                default_preset="4vcpu-16gb",
                build_spec=lambda pl, pr: created,
            )
    # No project survived routing => the submit loop (and its error-sweep) never ran.
    sweep.assert_not_called()
