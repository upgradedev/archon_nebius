"""
End-to-end test of the readiness gate itself.

This drives the REAL gate the way CI and a judge do — as a subprocess of
`scripts/readiness.py` — and asserts that the offline (`--skip-live`) path
computes >= 95% automatable completeness and exits 0. It deliberately does NOT
import the gate's internals: it exercises the whole thing end-to-end, including
the child pytest subprocesses the gate spawns and the readiness.json it writes.

It is intentionally independent of the live-service e2e fixtures (no
BACKEND_URL, no Docker, no S3) so it runs in the plain offline CI job. The gate
is run ONCE (module-scoped fixture) and its artifact shared across assertions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "readiness.py"
THRESHOLD = 95.0


@pytest.fixture(scope="module")
def gate_run(tmp_path_factory) -> dict:
    """Run the real gate once (offline) and return (proc, report)."""
    out = tmp_path_factory.mktemp("readiness") / "readiness.json"
    proc = subprocess.run(
        [sys.executable, str(GATE), "--skip-live", "--out", str(out)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900,
    )
    assert out.is_file(), (
        f"gate wrote no readiness.json\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return {"proc": proc, "report": json.loads(out.read_text(encoding="utf-8"))}


def test_readiness_gate_offline_meets_threshold(gate_run) -> None:
    proc, report = gate_run["proc"], gate_run["report"]
    pct = report["automatable_completeness_pct"]
    assert pct >= THRESHOLD, (
        f"automatable completeness {pct}% < {THRESHOLD}% gate\n"
        + "per-criterion: "
        + ", ".join(f"{k}={v['pct']}%" for k, v in report["criteria"].items())
        + f"\nSTDOUT:\n{proc.stdout}"
    )
    assert report["passed"] is True
    assert proc.returncode == 0, f"gate exited {proc.returncode} at {pct}%"


def test_readiness_report_shape_is_complete(gate_run) -> None:
    """The artifact must cover the six rubric criteria plus the security gate,
    and list user-gated items."""
    report = gate_run["report"]
    expected = {"technical", "reproducibility", "educational",
                "product_depth", "usefulness", "originality", "security"}
    assert set(report["criteria"]) == expected, (
        "gate must score the 6 rubric criteria + the security pen-test gate"
    )

    # Every scored check carries real evidence (never an empty string).
    for crit in report["criteria"].values():
        assert crit["checks"], "each criterion must have at least one check"
        for chk in crit["checks"]:
            assert chk["status"] in {"pass", "fail"}, chk
            assert chk["evidence"].strip(), f"check {chk['id']} has no evidence"

    # The live/signed-in items are surfaced but never counted in the score.
    gated_ids = {g["id"] for g in report["user_gated"]}
    assert {"live.health", "live.signed_in_e2e"} <= gated_ids


def test_product_depth_covers_all_six_primitives(gate_run) -> None:
    """Product-depth must assert all six Nebius primitives, each wired + tested."""
    depth = gate_run["report"]["criteria"]["product_depth"]["checks"]
    ids = {c["id"] for c in depth}
    assert len({i for i in ids if i.startswith("depth.p")}) == 6, ids
    for chk in depth:
        assert chk["status"] == "pass", f"primitive check regressed: {chk['id']} -> {chk['evidence']}"
