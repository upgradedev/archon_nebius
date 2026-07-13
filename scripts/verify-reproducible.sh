#!/usr/bin/env bash
#
# One-command, offline reproducibility path for Archon.
#
# A judge (or CI) can run THIS single script, with no cloud credentials and no
# network, and watch the headline claims reproduce from source:
#
#   1. the measured impact  — the naive bank-only floor understates workforce
#      cost by EUR 133,381.71 (~72% over the bank figure) on the 40-case corpus;
#   2. the pipeline smoke    — every OFFLINE agent suite passes (the extraction
#      and analysis pipelines run end-to-end against deterministic Fake/mocked
#      clients — no Inference API, no S3, no Postgres);
#   3. the readiness gate    — scripts/readiness.py reports automatable
#      completeness against the 6 Nebius judging criteria.
#
# Everything here is deterministic and costs EUR 0 (no API key). The only
# dependency is the three Python requirements files (pydantic, pytest, ...).
#
# Usage:
#   bash scripts/verify-reproducible.sh
#
# Exit code 0 == the repo reproduced its own headline numbers and passed the
# offline suites and the readiness gate. Non-zero == a claim did not reproduce.

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

PY="${PYTHON:-python}"
command -v "$PY" >/dev/null 2>&1 || PY="python3"

hr() { printf '%s\n' "────────────────────────────────────────────────────────────"; }

echo
hr
echo "Archon — offline reproducibility check (no network, no API key, EUR 0)"
hr

# ── 1. Measured impact: the ~72% / EUR 133,381.71 figure from the full corpus ──
echo
echo "[1/3] Reproducing the measured impact from the 40-case labelled corpus ..."
RESULTS_TMP="$(mktemp -t archon-repro-XXXXXX.json)"
trap 'rm -f "$RESULTS_TMP"' EXIT

"$PY" eval/evaluate.py --corpus eval/corpus/full --out "$RESULTS_TMP" >/dev/null

"$PY" - "$RESULTS_TMP" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
floor = data["naive_floor"]
recovered = round(floor["total_understatement"], 2)
pct_bank = floor["mean_understatement_pct_of_bank"]
wedge = floor["mean_employer_social_security_wedge_pct_of_bank"]

# The README / blog / eval/BASELINE.md headline numbers, asserted from source.
EXPECT_RECOVERED = 133381.71
assert abs(recovered - EXPECT_RECOVERED) < 0.5, (
    f"understatement drifted: got {recovered}, expected {EXPECT_RECOVERED}")
assert 68.0 <= pct_bank <= 76.0, f"~72% figure drifted: {pct_bank}%"
assert 30.0 <= wedge <= 40.0, f"~35% employer wedge drifted: {wedge}%"

print(f"    OK  understatement recovered = EUR {recovered:,.2f}  (expected {EXPECT_RECOVERED:,.2f})")
print(f"    OK  mean understatement       = {pct_bank}% over the bank figure (~72%)")
print(f"    OK  employer social-sec wedge = {wedge}% of the bank figure (~35%)")
PYEOF

# ── 2. Offline pipeline smoke: every agent suite that runs without the cloud ──
echo
echo "[2/3] Running the OFFLINE pipeline suites (Fake/mocked clients) ..."
# Each suite is a separate pytest process: the extraction and analysis pipelines
# ship identically-named top-level `models`/`agents` packages that collide in one
# interpreter (same reason scripts/coverage.sh runs them separately).
OFFLINE_SUITES=(
  "backend/tests"
  "jobs/extraction/tests"
  "jobs/analysis/tests"
  "eval/tests"
)
for suite in "${OFFLINE_SUITES[@]}"; do
  echo "    ── pytest $suite ──"
  "$PY" -m pytest "$suite" -q
done

# ── 3. Readiness gate: automatable completeness across the 6 judging criteria ──
echo
echo "[3/3] Running the readiness gate ..."
"$PY" scripts/readiness.py

echo
hr
echo "REPRODUCIBLE: headline impact reproduced, offline suites green, gate passed."
hr
