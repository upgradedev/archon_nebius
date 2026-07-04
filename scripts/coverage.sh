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

echo "── enforcing global gate: fail-under ${FAIL_UNDER}% ───────────────────"
python -m coverage report --fail-under="${FAIL_UNDER}"

# Diff-coverage gate (opt-in): even when the global blend clears its bar, a PR
# that adds poorly-tested NEW lines must be caught. Enabled by exporting
# DIFF_COVER_COMPARE_BRANCH (e.g. origin/master); CI sets it on pull_request.
# coverage.xml is written with relative_files=True (see .coveragerc) so its
# paths are repo-relative and diff-cover can map them onto git's diff.
if [[ -n "${DIFF_COVER_COMPARE_BRANCH:-}" ]]; then
  DIFF_FAIL_UNDER="${DIFF_COVER_FAIL_UNDER:-80}"
  echo "── diff-coverage gate: changed lines ≥ ${DIFF_FAIL_UNDER}% vs ${DIFF_COVER_COMPARE_BRANCH} ──"
  python -m diff_cover.diff_cover_tool coverage.xml \
    --compare-branch="${DIFF_COVER_COMPARE_BRANCH}" \
    --fail-under="${DIFF_FAIL_UNDER}"
else
  echo "── diff-coverage gate: skipped (DIFF_COVER_COMPARE_BRANCH unset) ──────"
fi
