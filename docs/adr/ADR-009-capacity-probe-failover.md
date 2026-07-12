# ADR-009 — Compute preset failover ladder for Job provisioning (capacity probe)

**Date:** 2026-07-01
**Status:** Active

## Context

A Nebius AI Job is a *request* for compute, not a guarantee. Quota is granted
per compute preset, and a silent zero-quota incident showed the worst failure
mode: the `cpu-d3` AI-Jobs quota was 0, so every submitted Job was *accepted*,
stranded in `PROVISIONING`, never allocated an instance, and torn down with no
clean error. The submission returned a job id; nothing ever ran. The pipeline
stalled invisibly.

`cpu-d3` is the only CPU platform in `eu-west1`, so the realistic fallback is a
larger preset *size* within it (Jobs quota is granted per size).

## Decision

Nebius AI Job submission (extraction + analysis) walks a config-driven, ordered,
bounded preset ladder (`JOB_PRESET_LADDER`, default = the live per-job preset,
then the next larger `cpu-d3` size). After each submission a short bounded
provisioning probe classifies the outcome. Archon fails over to the next preset
**only** when a job never provisioned — a terminal failure
(`FAILED`/`CANCELLED`/`ERROR`) with zero instances that was never `RUNNING`, a
job that vanished mid-provisioning, or a `FAILED_PRECONDITION`/quota error at
submission. A job that reached compute (`RUNNING`/instances/`started_at`) and
then failed is surfaced immediately with **no** failover — retrying it would
mask an application bug and waste money. When every rung fails to provision, the
service raises `ComputeCapacityUnavailable`, mapped to **HTTP 503**.

## Consequences

- A config-driven ladder (extend via `JOB_PRESET_LADDER`; probe tunables
  `JOB_PROVISION_PROBE_SECS` / `JOB_PROVISION_POLL_SECS`). Each rung is tried at
  most once; never-provisioned scaffolding is deleted before the next attempt
  (no leaked jobs).
- Worst-case added latency is ~one probe window (~30 s, optimistic-return) —
  under the Firebase 60 s / axios 120 s ceilings.
- The 503 guarantee covers terminal/vanished failures; a job that hangs
  *forever* in `PROVISIONING` returns `pending` + a loud WARNING (deliberate:
  never kill a healthy slow job).
- Shipped in PR #81; introduced the shared `_submit_job_with_failover` helper
  (DRY across extraction + analysis) and the real-pysdk `JobStatus` shape
  contract test. Also fixed a latent bug — `JobStatus` exposes `check_presence()`,
  not `HasField()`.

## References

- Full failure taxonomy, the GPU-only capacity-API finding, and the flow
  diagram: [`docs/capacity-probe-pattern.md`](../capacity-probe-pattern.md)
- One-command offline reproduction: `bash scripts/demo-failover.sh`
- Implementation: `backend/services/nebius.py` (`_submit_job_with_failover`)
- Contract test: `backend/tests/test_nebius_service.py`
