#!/usr/bin/env python3
"""
Archon readiness gate — machine-checkable submission completeness.

Encodes the SIX equal Nebius judging criteria (technical implementation,
reproducibility, educational content, product-usage depth, real-world
usefulness, originality) as concrete machine checks backed by REAL evidence:
not "does a file exist" but "is the cited symbol wired into the cited file AND
does the cited offline test actually pass". It also reproduces the headline
measured figure (EUR 133,381.71 / ~72%) from the corpus, in-process.

Each check resolves to one of three states:

    pass         evidence exists and is verified now
    fail         evidence is missing or a cited test failed
    user_gated   depends on the LIVE deployment / signed-in session — probed
                 for information, but NEVER counted against the automatable
                 score (a judge/user must confirm these on the live site)

The gate prints a per-criterion report, computes a weighted completeness %
over the AUTOMATABLE criteria (the six criteria weighted equally, matching the
rubric), writes readiness.json, and exits non-zero if that % < THRESHOLD.

Design notes
------------
* Paths are anchored to the repo root via __file__, never cwd, so the gate
  behaves identically from CI, from the reproducibility script's subprocess,
  and from a local shell.
* Only OFFLINE test suites are cited as evidence (backend / jobs-extraction /
  jobs-analysis / eval). The live e2e suite and anything needing Docker, S3,
  Postgres or a BACKEND_URL is deliberately NOT cited — those surfaces are the
  user_gated checks.
* Test runs are memoised: each cited test file is executed at most once even if
  several checks depend on it.

Usage:
    python scripts/readiness.py                 # full gate + readiness.json
    python scripts/readiness.py --skip-live     # do not probe the live endpoint
    python scripts/readiness.py --out PATH       # custom readiness.json path
    python scripts/readiness.py --quiet          # only the summary line
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 95.0
LIVE_HEALTH_URL = "https://archon-pnl.web.app/api/health"
LIVE_AUTH_URL = "https://archon-pnl.web.app/api/periods"

PASS, FAIL, USER_GATED = "pass", "fail", "user_gated"


# ─────────────────────────────────────────────────────────────────────────────
# Evidence primitives
# ─────────────────────────────────────────────────────────────────────────────
def _read(relpath: str) -> str | None:
    p = REPO_ROOT / relpath
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def file_contains(relpath: str, *patterns: str) -> tuple[bool, str]:
    """True iff `relpath` exists and every regex in `patterns` matches it."""
    text = _read(relpath)
    if text is None:
        return False, f"missing file: {relpath}"
    missing = [p for p in patterns if not re.search(p, text)]
    if missing:
        return False, f"{relpath}: pattern(s) not found: {', '.join(missing)}"
    return True, f"{relpath}: wired ({', '.join(patterns)})"


def file_absent_pattern(relpath: str, pattern: str) -> tuple[bool, str]:
    """True iff `relpath` exists and does NOT contain `pattern` (negative check)."""
    text = _read(relpath)
    if text is None:
        return False, f"missing file: {relpath}"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return False, f"{relpath}: FORBIDDEN pattern present: {m.group(0)!r}"
    return True, f"{relpath}: clean (no /{pattern}/)"


_PYTEST_CACHE: dict[str, tuple[bool, str]] = {}


def run_pytest(target: str) -> tuple[bool, str]:
    """Run one offline pytest target (repo-relative) in an isolated subprocess.

    Memoised so a test file cited by several checks runs only once. The
    extraction and analysis pipelines ship colliding top-level package names, so
    each target MUST run in its own process — which is exactly what happens here.
    """
    if target in _PYTEST_CACHE:
        ok, _ = _PYTEST_CACHE[target]
        return ok, _PYTEST_CACHE[target][1] + " (cached)"
    cmd = [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600
        )
    except Exception as exc:  # pragma: no cover - defensive
        res = (False, f"pytest {target}: launch error: {exc}")
        _PYTEST_CACHE[target] = res
        return res
    ok = proc.returncode == 0
    tail = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
    res = (ok, f"pytest {target}: {'PASS' if ok else 'FAIL'} -> {tail}")
    _PYTEST_CACHE[target] = res
    return res


_EVAL_CACHE: dict[str, object] = {}


def eval_full_corpus() -> dict:
    """Run the real eval harness on the 40-case corpus, return naive_floor.

    Reproduces the headline measured figure offline (no API key). Memoised.
    """
    if "floor" in _EVAL_CACHE:
        return _EVAL_CACHE["floor"]  # type: ignore[return-value]
    fd, tmp_name = tempfile.mkstemp(prefix="archon-readiness-", suffix=".json")
    os.close(fd)  # let the subprocess own the file (Windows can't share the fd)
    out = Path(tmp_name)
    try:
        proc = subprocess.run(
            [sys.executable, "eval/evaluate.py", "--corpus", "eval/corpus/full",
             "--out", str(out)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            floor = {"error": proc.stderr.strip()[-300:] or "eval failed"}
        else:
            floor = json.loads(out.read_text(encoding="utf-8"))["naive_floor"]
    except Exception as exc:  # pragma: no cover - defensive
        floor = {"error": str(exc)}
    finally:
        out.unlink(missing_ok=True)
    _EVAL_CACHE["floor"] = floor
    return floor


def check_headline_figure() -> tuple[str, str]:
    """The eval floor reproduces EUR 133,381.71 / ~72% / ~35% from source."""
    floor = eval_full_corpus()
    if "error" in floor:
        return FAIL, f"eval harness did not run: {floor['error']}"
    recovered = round(float(floor["total_understatement"]), 2)
    pct_bank = float(floor["mean_understatement_pct_of_bank"])
    wedge = float(floor["mean_employer_social_security_wedge_pct_of_bank"])
    if abs(recovered - 133381.71) >= 0.5:
        return FAIL, f"understatement drifted: {recovered} != 133381.71"
    if not (68.0 <= pct_bank <= 76.0):
        return FAIL, f"~72% figure drifted: {pct_bank}%"
    if not (30.0 <= wedge <= 40.0):
        return FAIL, f"~35% wedge drifted: {wedge}%"
    return PASS, (f"eval floor reproduces EUR {recovered:,.2f} "
                  f"({pct_bank}% over bank, wedge {wedge}%)")


def probe_live(url: str, timeout: float = 6.0) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status, f"{url} -> HTTP {r.status}"
    except urllib.error.HTTPError as e:  # a 401/403/etc is still a live response
        return e.code, f"{url} -> HTTP {e.code}"
    except Exception as e:
        return None, f"{url} -> unreachable ({type(e).__name__})"


# ─────────────────────────────────────────────────────────────────────────────
# Check + criterion model
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Check:
    cid: str
    desc: str
    fn: Callable[[], tuple[str, str]]
    kind: str = "auto"          # "auto" | "user_gated"
    status: str = ""
    evidence: str = ""

    def run(self) -> None:
        try:
            self.status, self.evidence = self.fn()
        except Exception as exc:  # pragma: no cover - defensive
            self.status, self.evidence = FAIL, f"check raised: {exc!r}"
        # Some evidence primitives (file_contains, run_pytest) return a bool
        # status; normalise those to the pass/fail vocabulary.
        if isinstance(self.status, bool):
            self.status = PASS if self.status else FAIL
        # A user_gated check never fails the score; normalise its verdict.
        if self.kind == "user_gated" and self.status == FAIL:
            self.status = USER_GATED


@dataclass
class Criterion:
    key: str
    title: str
    checks: list[Check] = field(default_factory=list)

    @property
    def auto_checks(self) -> list[Check]:
        return [c for c in self.checks if c.kind == "auto"]

    @property
    def pct(self) -> float:
        auto = self.auto_checks
        if not auto:                      # all user_gated -> not scorable
            return 100.0
        passed = sum(1 for c in auto if c.status == PASS)
        return passed / len(auto) * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# The rubric encoded as checks (each backed by real evidence)
# ─────────────────────────────────────────────────────────────────────────────
def build_criteria(skip_live: bool) -> list[Criterion]:
    def live_check(url: str, expect_live_codes: tuple[int, ...], label: str):
        def _fn() -> tuple[str, str]:
            if skip_live:
                return USER_GATED, f"{label}: skipped (--skip-live)"
            code, msg = probe_live(url)
            # These are ALWAYS user_gated (they depend on the live deploy the
            # user owns); the probe is informational only.
            if code in expect_live_codes:
                return USER_GATED, f"{label}: LIVE ({msg}) — user confirms"
            return USER_GATED, f"{label}: not confirmed ({msg}) — user action"
        return _fn

    return [
        Criterion("technical", "Technical implementation", [
            Check("tech.failover.wired",
                  "Capacity-probe failover ladder wired in the job submitter",
                  lambda: file_contains("backend/services/nebius.py",
                                        r"_submit_job_with_failover",
                                        r"ComputeCapacityUnavailable",
                                        r"JOB_PRESET_LADDER")),
            Check("tech.failover.tested",
                  "Failover ladder + JobStatus contract has a passing test",
                  lambda: run_pytest("backend/tests/test_nebius_service.py")),
            Check("tech.injection.wired",
                  "Deterministic prompt-injection scan wired into extraction",
                  _injection_wired),
            Check("tech.injection.tested",
                  "Injection scan has a passing test",
                  lambda: run_pytest("jobs/extraction/tests/test_injection_scan.py")),
            Check("tech.deterministic.numbers",
                  "P&L figures are pure Python arithmetic (LLM only narrates)",
                  lambda: file_contains("jobs/analysis/agents/pnl_builder.py", r"round\(")),
            Check("tech.deterministic.tested",
                  "Deterministic P&L builder has a passing test",
                  lambda: run_pytest("jobs/analysis/tests/test_pnl_builder.py")),
        ]),

        Criterion("reproducibility", "Reproducibility", [
            Check("repro.script.exists",
                  "One-command offline path (scripts/verify-reproducible.sh)",
                  lambda: file_contains("scripts/verify-reproducible.sh",
                                        r"eval/evaluate\.py", r"readiness\.py")),
            Check("repro.readme.documents",
                  "README documents the one-command reproducibility path",
                  lambda: file_contains("README.md", r"verify-reproducible\.sh")),
            Check("repro.headline.reproduces",
                  "Offline eval reproduces the headline figure from source",
                  check_headline_figure),
            Check("repro.eval.tested",
                  "Eval baselines are asserted by a passing test suite",
                  lambda: run_pytest("eval/tests")),
        ]),

        Criterion("educational", "Educational content quality", [
            Check("edu.blog.substantial",
                  "Engineering blog post present and substantial (>5 KB)",
                  _blog_substantial),
            Check("edu.blog.grounded",
                  "Blog references the eval harness and the measured figure",
                  lambda: file_contains("demo/blog-post.md", r"eval/", r"133,381")),
            Check("edu.no_stale_gap",
                  "No superseded '28% payroll gap' number in README/blog",
                  _no_stale_gap),
        ]),

        Criterion("product_depth", "Product-usage depth (6 Nebius primitives)", [
            Check("depth.p1.endpoint",
                  "AI Endpoint: FastAPI app wired + health test passes",
                  lambda: _wired_and_tested(
                      ("backend/main.py", (r"FastAPI",)),
                      "backend/tests/test_health.py")),
            Check("depth.p2.jobs",
                  "AI Jobs: JobServiceClient/CreateJobRequest wired + test passes",
                  lambda: _wired_and_tested(
                      ("backend/services/nebius.py", (r"JobServiceClient", r"CreateJobRequest")),
                      "backend/tests/test_nebius_service.py")),
            Check("depth.p3.inference",
                  "Inference API: OpenAI client on NEBIUS base url + narrator test",
                  lambda: _wired_and_tested(
                      ("jobs/analysis/agents/narrator.py", (r"NEBIUS_INFERENCE_BASE_URL", r"OpenAI")),
                      "jobs/analysis/tests/test_narrator.py")),
            Check("depth.p4.storage",
                  "Object Storage: boto3 on STORAGE_ENDPOINT + storage test passes",
                  lambda: _wired_and_tested(
                      ("backend/services/storage.py", (r"boto3", r"endpoint_url")),
                      "backend/tests/test_storage.py")),
            Check("depth.p5.postgres",
                  "Managed PostgreSQL: psycopg2 models + db test passes",
                  lambda: _wired_and_tested(
                      ("backend/db/models.py", (r"psycopg2",)),
                      "backend/tests/test_db_models.py")),
            Check("depth.p6.registry",
                  "Container Registry: image push in deploy + credentials test",
                  lambda: _wired_and_tested(
                      ("nebius/redeploy.sh", (r"(?i)registry|docker push|cr\.eu-west1",)),
                      "backend/tests/test_redeploy_credentials.py")),
        ]),

        Criterion("usefulness", "Real-world usefulness", [
            Check("useful.figure.consistent",
                  "Measured figure (133,381 / 72%) consistent across README, eval, blog",
                  _figure_consistent),
            Check("useful.floor.recovers",
                  "Naive-floor eval recovers the measured understatement",
                  check_headline_figure),
            Check("useful.reconciliation.wired",
                  "Completeness (statement-vs-invoice) agent wired + tested",
                  lambda: _wired_and_tested(
                      ("jobs/analysis/main.py", (r"reconciliation_agent",)),
                      "jobs/analysis/tests/test_reconciliation_agent.py")),
        ]),

        Criterion("originality", "Originality", [
            Check("orig.adr.present",
                  "ADR-009 (capacity-probe failover) documented in-repo",
                  lambda: file_contains("docs/adr/ADR-009-capacity-probe-failover.md",
                                        r"(?i)failover", r"(?i)capacity")),
            Check("orig.pattern.doc",
                  "Capacity-probe pattern write-up present",
                  lambda: file_contains("docs/capacity-probe-pattern.md", r"(?i)capacity")),
            Check("orig.three_points",
                  "All 3 originality points surfaced in README "
                  "(failover / injection-fence / reconciliation)",
                  lambda: file_contains("README.md",
                                        r"ADR-009",
                                        r"injection_scan\.py",
                                        r"ReconciliationAgent")),
        ]),

        Criterion("user_gated", "Live-deployment checks (user-gated, not scored)", [
            Check("live.health",
                  "Live endpoint /api/health returns 200 behind the BFF",
                  live_check(LIVE_HEALTH_URL, (200,), "live /api/health"),
                  kind="user_gated"),
            Check("live.auth_gate",
                  "Live BFF auth gate returns 401 unauthenticated",
                  live_check(LIVE_AUTH_URL, (401, 403), "live /api/periods auth gate"),
                  kind="user_gated"),
            Check("live.signed_in_e2e",
                  "Signed-in end-to-end upload renders a report (needs login creds)",
                  lambda: (USER_GATED,
                           "signed-in E2E needs live login creds — run e2e/test_05_signed_in.py "
                           "against the live site; not headless-automatable here"),
                  kind="user_gated"),
        ]),
    ]


# ── composite evidence helpers (defined after primitives; used above) ────────
def _wired_and_tested(wiring: tuple[str, tuple[str, ...]], test_target: str) -> tuple[str, str]:
    relpath, patterns = wiring
    ok, ev = file_contains(relpath, *patterns)
    if not ok:
        return FAIL, ev
    tok, tev = run_pytest(test_target)
    if not tok:
        return FAIL, tev
    return PASS, f"{ev}; {tev}"


def _injection_wired() -> tuple[str, str]:
    ok1, ev1 = file_contains("jobs/extraction/main.py", r"scan_document")
    if not ok1:
        return FAIL, ev1
    ok2, ev2 = file_contains("jobs/extraction/injection_scan.py", r"INJECTION_PATTERNS")
    if not ok2:
        return FAIL, ev2
    return PASS, f"{ev1}; {ev2}"


def _blog_substantial() -> tuple[str, str]:
    text = _read("demo/blog-post.md")
    if text is None:
        return FAIL, "missing demo/blog-post.md"
    n = len(text)
    if n < 5000:
        return FAIL, f"demo/blog-post.md too short ({n} chars < 5000)"
    return PASS, f"demo/blog-post.md present ({n:,} chars)"


def _no_stale_gap() -> tuple[str, str]:
    # Context-scoped: a bare "28%" false-positives on the "28.4% operating
    # margin" in the sample output. Only flag 28% used as the payroll GAP.
    forbidden = r"28\s*%[^.\n]{0,40}(gap|understat|over the bank|payroll cost)"
    forbidden2 = r"(gap|understat|over the bank|payroll cost)[^.\n]{0,40}\b28\s*%"
    for rel in ("README.md", "demo/blog-post.md"):
        for pat in (forbidden, forbidden2):
            ok, ev = file_absent_pattern(rel, pat)
            if not ok:
                return FAIL, ev
    return PASS, "no superseded '28% gap' phrasing in README/blog"


def _figure_consistent() -> tuple[str, str]:
    targets = {"README.md": None, "eval/BASELINE.md": None, "demo/blog-post.md": None}
    for rel in targets:
        ok_num, ev_num = file_contains(rel, r"133,381")
        ok_pct, ev_pct = file_contains(rel, r"72\s*%")
        if not ok_num:
            return FAIL, f"133,381 missing from {rel}"
        if not ok_pct:
            return FAIL, f"72% missing from {rel}"
    return PASS, "133,381 + 72% present + consistent in README, eval/BASELINE, blog"


# ─────────────────────────────────────────────────────────────────────────────
# Runner / reporting
# ─────────────────────────────────────────────────────────────────────────────
_ICON = {PASS: "PASS", FAIL: "FAIL", USER_GATED: "GATE"}


def main() -> int:
    # UTF-8 stdout so the report renders identically on Windows (cp1252) and CI.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Archon submission readiness gate.")
    ap.add_argument("--out", default=str(REPO_ROOT / "readiness.json"),
                    help="path for the machine-readable readiness.json")
    ap.add_argument("--skip-live", action="store_true",
                    help="do not probe the live endpoint (fully offline)")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line")
    args = ap.parse_args()

    criteria = build_criteria(skip_live=args.skip_live)
    for crit in criteria:
        for chk in crit.checks:
            chk.run()

    scored = [c for c in criteria if c.key != "user_gated"]
    automatable_pct = round(sum(c.pct for c in scored) / len(scored), 2)
    passed_gate = automatable_pct >= THRESHOLD

    # ---- report ----
    if not args.quiet:
        print()
        print("=" * 74)
        print(" ARCHON READINESS GATE — 6 Nebius judging criteria (equal weight)")
        print("=" * 74)
        for crit in scored:
            print(f"\n[{crit.pct:5.1f}%] {crit.title}")
            for c in crit.checks:
                print(f"   {_ICON[c.status]}  {c.cid:<28} {c.desc}")
                print(f"         -> {c.evidence}")

        gated = next((c for c in criteria if c.key == "user_gated"), None)
        if gated:
            print("\n" + "-" * 74)
            print(" USER-GATED (not counted — confirm on the live deployment):")
            for c in gated.checks:
                print(f"   {_ICON[c.status]}  {c.cid:<28} {c.desc}")
                print(f"         -> {c.evidence}")

        print("\n" + "=" * 74)
        print(f" Per-criterion: " + " | ".join(f"{c.key} {c.pct:.0f}%" for c in scored))
        print(f" AUTOMATABLE COMPLETENESS: {automatable_pct:.2f}%   "
              f"(threshold {THRESHOLD:.0f}% -> {'PASS' if passed_gate else 'FAIL'})")
        print("=" * 74)

    # ---- artifact ----
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_pct": THRESHOLD,
        "automatable_completeness_pct": automatable_pct,
        "passed": passed_gate,
        "criteria": {
            c.key: {
                "title": c.title,
                "pct": round(c.pct, 2),
                "checks": [
                    {"id": ch.cid, "desc": ch.desc, "kind": ch.kind,
                     "status": ch.status, "evidence": ch.evidence}
                    for ch in c.checks
                ],
            } for c in scored
        },
        "user_gated": [
            {"id": ch.cid, "desc": ch.desc, "status": ch.status, "evidence": ch.evidence}
            for c in criteria if c.key == "user_gated" for ch in c.checks
        ],
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"\nWrote {args.out}")

    print(f"readiness: {automatable_pct:.2f}% automatable completeness "
          f"({'PASS' if passed_gate else 'FAIL'} at {THRESHOLD:.0f}% gate)")
    return 0 if passed_gate else 1


if __name__ == "__main__":
    sys.exit(main())
