#!/usr/bin/env python3
"""One-command, offline demo of the Accept-then-Stall Capacity Probe + Failover
Ladder (see docs/capacity-probe-pattern.md, ADR-009).

This drives the *real* `_submit_job_with_failover` from
`backend/services/nebius.py`. The only things mocked are the Nebius SDK boundary
(so no credentials, no network, and no billable job are needed) and the
provisioning *outcomes* — exactly the way the CI unit tests do it. The failover
logic under test is production code, unmodified.

Scenario:
  * `JOB_PRESET_LADDER` = a deliberately-UNPROVISIONABLE first rung followed by a
    working second rung.
  * Rung 1 is accepted but stalls in PROVISIONING with zero instances past the
    probe deadline (the accept-then-stall zero-capacity signature).
  * The probe classifies it `_NEVER_PROVISIONED`, deletes the scaffolding, and
    fails over to rung 2, which allocates an instance and runs.

Run it:
    bash scripts/demo-failover.sh
or directly:
    PYTHONPATH=backend python scripts/demo_failover.py
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make `services.nebius` importable regardless of the caller's cwd.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Deliberately-unprovisionable first rung, working second rung. These are real
# cpu-d3 preset sizes; rung 1 stands in for the zero-quota preset from the
# original incident.
LADDER = "cpu-d3:4vcpu-16gb,cpu-d3:8vcpu-32gb"


def _wrap(value):
    """SDK operation shape: .wait() resolves to `value`."""
    op = MagicMock()
    op.wait.return_value = value
    return op


def _make_status(state: int, instances: int, started: bool, message: str = ""):
    """Fake JobStatus mirroring the pysdk wrapper's field surface."""
    status = MagicMock()
    status.state = state
    status.instances = [MagicMock() for _ in range(instances)]
    status.check_presence.side_effect = lambda name: started if name == "started_at" else False
    status.state_details = MagicMock()
    status.state_details.message = message
    return status


def _make_job(job_id: str, status):
    job = MagicMock()
    job.metadata = MagicMock(id=job_id)
    job.resource_id = job_id          # create(...).wait() -> Operation.resource_id
    job.status = status
    return job


def _build_service():
    """A JobServiceClient stand-in that simulates the project + preset failover scenario."""
    service = MagicMock()
    # 4 create attempts:
    # 1. project-1 preset-1 -> job-1-1 (stalls)
    # 2. project-1 preset-2 -> job-1-2 (stalls)
    # 3. project-2 preset-1 -> job-2-1 (stalls)
    # 4. project-2 preset-2 -> job-2-2 (succeeds)
    service.create.side_effect = [
        _wrap(_make_job("job-1-1", _make_status(state=3, instances=1, started=True))),
        _wrap(_make_job("job-1-2", _make_status(state=3, instances=1, started=True))),
        _wrap(_make_job("job-2-1", _make_status(state=3, instances=1, started=True))),
        _wrap(_make_job("job-2-2", _make_status(state=3, instances=1, started=True))),
    ]
    stalled1 = _make_job("job-1-1", _make_status(state=1, instances=0, started=False))
    stalled2 = _make_job("job-1-2", _make_status(state=1, instances=0, started=False))
    stalled3 = _make_job("job-2-1", _make_status(state=1, instances=0, started=False))
    running = _make_job("job-2-2", _make_status(state=3, instances=1, started=True))
    service.get.side_effect = [
        _wrap(stalled1),
        _wrap(stalled2),
        _wrap(stalled3),
        _wrap(running)
    ]
    service.delete.return_value = _wrap(MagicMock())
    return service


def run_demo() -> dict:
    """Execute the failover against the real orchestrator. Returns a summary dict."""
    # Zero-length probe window so the accept-then-stall deadline fires instantly.
    os.environ["NEBIUS_PROJECT_ID"] = "project-demo"
    os.environ["NEBIUS_PROJECT_ID_LADDER"] = "project-1,project-2"
    os.environ["NEBIUS_SUBNET_ID"] = "subnet-demo"
    os.environ["JOB_PRESET_LADDER"] = LADDER
    os.environ["JOB_PROVISION_PROBE_SECS"] = "0"
    os.environ["JOB_PROVISION_POLL_SECS"] = "0"

    from services import nebius as svc

    service = _build_service()
    sdk = MagicMock()

    print("=" * 72)
    print("Accept-then-Stall Capacity Probe + Failover Ladder — offline demo")
    print("=" * 72)
    projects = svc._project_ladder()
    ladder = svc._preset_ladder("cpu-d3", "4vcpu-16gb")
    print(f"NEBIUS_PROJECT_ID_LADDER = project-1,project-2")
    print(f"Resolved projects        = {projects}")
    print(f"JOB_PRESET_LADDER        = {LADDER}")
    print(f"Resolved presets         = {ladder}")
    print(f"Probe window             = {svc._provision_probe_secs()}s "
          f"(0 => accept-then-stall deadline fires immediately)")
    print("-" * 72)
    print("BEFORE: submitting on project-1 preset 1...\n")

    with ExitStack() as stack:
        stack.enter_context(patch.object(svc, "_make_sdk", return_value=sdk))
        stack.enter_context(patch.object(svc, "_delete_nebius_error_jobs"))
        stack.enter_context(patch("nebius.api.nebius.ai.v1.JobServiceClient", return_value=service))
        stack.enter_context(patch("nebius.api.nebius.ai.v1.CreateJobRequest", side_effect=lambda **kw: MagicMock(**kw)))
        stack.enter_context(patch("nebius.api.nebius.ai.v1.GetJobRequest", side_effect=lambda **kw: MagicMock(**kw)))
        stack.enter_context(patch("nebius.api.nebius.ai.v1.DeleteJobRequest", side_effect=lambda **kw: MagicMock(**kw)))
        stack.enter_context(patch("nebius.api.nebius.common.v1.ResourceMetadata", side_effect=lambda **kw: MagicMock(**kw)))

        result = svc._submit_job_with_failover(
            name_prefix="archon-demo",
            period="2026-07",
            default_platform="cpu-d3",
            default_preset="4vcpu-16gb",
            build_spec=lambda platform, preset: {"platform": platform, "preset": preset},
        )

    print("\n" + "-" * 72)
    print("AFTER: the ladder healed itself.")
    print(f"  rungs attempted (create calls) : {service.create.call_count}")
    print(f"  stalled scaffolding deleted     : {service.delete.call_count}")
    print(f"  final running job id            : {result['id']}")
    print(f"  final job status                : {result['status']}")
    print("=" * 72)

    failed_over = service.create.call_count == 4 and result["id"] == "job-2-2"
    print("RESULT:", "FAILOVER SUCCEEDED (project-1 presets stalled -> project-2 preset-2 running)."
          if failed_over else "UNEXPECTED — demo did not fail over as designed.")

    return {
        "result": result,
        "create_calls": service.create.call_count,
        "delete_calls": service.delete.call_count,
        "final_job_id": result["id"],
        "failed_over": failed_over,
    }


def main() -> int:
    # Force UTF-8 stdout so the log narration renders cleanly on consoles that
    # default to a legacy code page (e.g. Windows cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    # Surface the production code's own log narration so the reader watches the
    # REAL failover decisions, not a scripted retelling.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("    [log] %(levelname)s %(message)s"))
    svc_logger = logging.getLogger("services.nebius")
    svc_logger.setLevel(logging.INFO)
    svc_logger.addHandler(handler)

    summary = run_demo()
    return 0 if summary["failed_over"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
