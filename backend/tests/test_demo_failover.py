"""CI coverage for the one-command failover demo (scripts/demo_failover.py).

Wires the reproducible demo into CI so `bash scripts/demo-failover.sh` cannot
silently rot — Reproducibility is the challenge tiebreaker. The demo drives the
REAL `_submit_job_with_failover`; this test imports its `run_demo()` directly
(no subprocess, no cwd/env flakiness) and asserts the ladder actually failed over
from the stalled rung to the working one.
"""
import os
import sys
from pathlib import Path

import pytest

# scripts/ lives at the repo root, one level above backend/.
_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# run_demo() writes these directly to os.environ (the pattern reads them via
# os.getenv), which bypasses monkeypatch's own restore. Snapshot + restore them
# so the demo cannot leak env state into any later test regardless of order.
_DEMO_ENV_VARS = (
    "NEBIUS_PROJECT_ID", "NEBIUS_PROJECT_ID_LADDER", "NEBIUS_SUBNET_ID", "JOB_PRESET_LADDER",
    "JOB_PROVISION_PROBE_SECS", "JOB_PROVISION_POLL_SECS",
)


@pytest.fixture(autouse=True)
def _restore_demo_env():
    saved = {k: os.environ.get(k) for k in _DEMO_ENV_VARS}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_demo_failover_runs_and_fails_over(capsys):
    # The demo imports nebius.api.* to patch it; skip cleanly if the SDK is absent.
    pytest.importorskip("nebius.api.nebius.ai.v1")

    import demo_failover

    summary = demo_failover.run_demo()

    # Real orchestrator behaviour: project-1 presets stalled -> deleted -> project-2 preset-2 ran.
    assert summary["failed_over"] is True
    assert summary["create_calls"] == 4          # 4 combinations attempted
    assert summary["delete_calls"] == 3          # 3 stalled scaffoldings cleaned up
    assert summary["final_job_id"] == "job-2-2"
    assert summary["result"]["status"] == "pending"

    # The human-facing before/after narration is actually printed.
    out = capsys.readouterr().out
    assert "BEFORE" in out and "AFTER" in out
    assert "FAILOVER SUCCEEDED" in out


def test_demo_module_main_returns_zero():
    pytest.importorskip("nebius.api.nebius.ai.v1")

    import demo_failover

    assert demo_failover.main() == 0
