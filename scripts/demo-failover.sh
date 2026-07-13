#!/usr/bin/env bash
# One-command, offline demo of the Capacity Probe + Failover Ladder
# (docs/capacity-probe-pattern.md, ADR-009).
#
# Runs entirely offline: no Nebius credentials, no network, no billable job.
# It mocks the Nebius SDK boundary and the provisioning outcomes, then drives the
# REAL `_submit_job_with_failover` so you can watch a preset that terminally fails
# to provision fail over to a working one.
#
#   bash scripts/demo-failover.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Put the backend package on the path so `services.nebius` imports cleanly.
export PYTHONPATH="${REPO_ROOT}/backend:${PYTHONPATH:-}"

PYTHON="${PYTHON:-python}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3

exec "$PYTHON" "${REPO_ROOT}/scripts/demo_failover.py"
