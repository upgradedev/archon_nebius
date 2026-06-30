#!/usr/bin/env bash
#
# Offline test-coverage gate for the Archon Python code (backend + extraction
# job + analysis endpoint + evaluation harness).
#
# Runs every OFFLINE test suite under pytest-cov and fails if total coverage
# drops below the threshold. No network, no Docker — only the three requirements
# files plus pytest-cov. Configuration (source dirs + documented omits) lives in
# .coveragerc at the repo root.
#
# Each suite runs as a SEPARATE pytest process and appends to one data file:
# the extraction pipeline (jobs/extraction) and the analysis pipeline
# (endpoints/analysis) ship identically-named top-level `models`/`agents`
# packages that collide if imported in the same interpreter.
#
# Usage:
#   bash scripts/coverage.sh                 # gate at the default threshold
#   COVERAGE_FAIL_UNDER=90 bash scripts/coverage.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

FAIL_UNDER="${COVERAGE_FAIL_UNDER:-85}"
export COVERAGE_FILE="${COVERAGE_FILE:-.coverage}"

python -m coverage erase

SUITES=(
  "backend/tests"
  "jobs/extraction/tests"
  "endpoints/analysis/tests"
  "eval/tests"
)

for suite in "${SUITES[@]}"; do
  echo "── coverage: $suite ───────────────────────────────────────────────"
  python -m pytest "$suite" -q --cov --cov-append --cov-config=.coveragerc
done

echo "── combined coverage report ───────────────────────────────────────────"
python -m coverage report
python -m coverage xml -o coverage.xml

echo "── enforcing gate: fail-under ${FAIL_UNDER}% ──────────────────────────"
python -m coverage report --fail-under="${FAIL_UNDER}"
