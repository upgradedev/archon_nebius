# ADR-010 — AI-Jobs quota pre-flight, and cross-region failover (future)

**Date:** 2026-07-13
**Status:** Partially Active — quota pre-flight **Active** (opt-in); cross-region failover **Proposed / future work**

## Context

ADR-009 gave Archon a preset-size failover ladder and a capacity probe, turning a
silent zero-quota stall into an eventual HTTP 503. But it still *submits, waits,
and fails*: with `cpu-d3` AI-Jobs quota at a hard 0 in `eu-west1`, every rung is
accepted, stranded in `PROVISIONING`, and torn down after ~30 minutes. The user
waits the full provision-then-FAIL cycle to learn something that was knowable up
front.

Two facts shape the fix:

1. **There is no "chance of launch" signal for CPU AI Jobs.** Nebius' Capacity
   Advisor (`AVAILABILITY_LEVEL_HIGH/MEDIUM/LOW/LIMIT_REACHED`) is documented as
   **GPU-VM-only** and *explicitly excludes* `cpu-d3` and AI Jobs. So a CPU Job
   does not fail from unlucky instance selection — it fails because quota is a
   deterministic **0**. Binary, not probabilistic. The right pre-flight is a
   **quota lookup**, not a capacity-availability guess.

2. **Serverless AI runs in all five public regions** (`eu-north1`, `eu-west1`,
   `me-west1`, `us-central1`, `uk-south1`), but Archon's Jobs are single-region:
   `build_spec` uses one hardcoded `NEBIUS_SUBNET_ID`, and the storage bucket,
   container registry, and PostgreSQL cluster all live in `eu-west1`. Quota is
   granted per region, so a different region may have quota where `eu-west1` has
   none — but reaching it needs region-local infrastructure.

## Decision

### Part A — Quota pre-flight, now an active routing SELECTOR (Active, opt-in)

Before submitting, `_submit_job_with_failover` calls `_route_projects_by_quota`,
which reads the AI-Jobs quota for every `(project, ladder-platform)` pair via
`QuotaAllowanceService.List` and actively **routes** the submission rather than
merely gating it:

- projects are **ordered** quota-available-first, then unknown;
- a project that is a **confirmed** hard 0 on *every* ladder platform is
  **dropped** (submitting there only provisions ~30 min then FAILs);
- a single confirmed-zero `(project, platform)` rung inside an otherwise-viable
  project is **skipped** in the submit loop;
- if **every** candidate is a confirmed 0, the request fails up front with
  `NoJobsQuota` (a `ComputeCapacityUnavailable` subclass → **HTTP 503**) — an
  instant, named error ("no AI-Jobs quota for cpu-d3 in region eu-west1") instead
  of a 30-minute doomed provision.

This supersedes the earlier single-project `_preflight_jobs_quota` gate for the
submit path: the gate raised on the *first* project's zero, which would have
killed a submission that could still succeed on a later project in the ladder.
The gate function is retained as a standalone tested utility.

Two guardrails make this safe to ship on a live submission:

- **Opt-in** via `JOB_QUOTA_PREFLIGHT` (default off). The exact quota resource
  name must be confirmed against a live tenant with real credentials before the
  selector can drop/reorder; until then it performs no lookups and behaviour is
  identical to today.
- **Fail-open** by contract. `_jobs_quota_state` returns `"unknown"` on any
  uncertainty — no matching quota row, an SDK build without the quotas API, or a
  lookup error — and `"unknown"` is never dropped (kept, ordered after
  available). The selector can only ever convert a *doomed* submission into a fast
  503 or reorder the ladder; it can never block one that might have succeeded.

### Part B — Cross-region failover (Proposed / future work)

Extend the ADR-009 ladder with a **region dimension**: each rung carries its own
`(region, subnet_id, registry image ref, storage endpoint)`. A per-region quota
pre-flight (Part A, run across regions) selects the first region whose AI-Jobs
quota is `> 0`, and the Job is submitted there. Ordering is config-driven, e.g.
`NEBIUS_REGION_LADDER=eu-west1,eu-north1,us-central1`.

This is **not implemented**. It is documented here as the deliberate next step so
the lever is captured, not lost.

## Consequences

- Part A ships as pure upside behind a flag: quota-ordered routing across the
  project ladder, zero-quota projects/rungs skipped, and an instant region-named
  503 when everything is a confirmed 0 — all once enabled; no behaviour change and
  no quota lookups while off. Covered by `backend/tests/test_quota_preflight.py`
  (state matching + gate + selector ordering/drop/fail-open + all-zero submit
  raises `NoJobsQuota` without creating a job). Adds `JOB_QUOTA_PREFLIGHT`,
  `NEBIUS_TENANT_ID` env knobs (`NEBIUS_REGION` already existed). `DATABASE_URL`
  is now injected into the backend Endpoint at deploy so the PG read-model mirror
  actually writes (was previously unset → silent no-op).
- Part B is deferred, not declined, because it is a real infrastructure lift and
  **untestable locally** (no reachable multi-region infra, IP-allowlisted PG):
  - Each candidate region needs its own subnet, a registry image it can pull
    (regional registries → push per region or configure cross-region pull), and
    reachable storage. Cross-region Object Storage reads incur latency + egress.
  - PostgreSQL is single-region and IP-allowlisted; a Job in another region does
    not touch it anyway (per ADR on the PG read-model, jobs write only S3 and the
    backend mirrors to PG), so this is not a blocker — but the backend↔PG path
    stays pinned to `eu-west1`.
  - Building and verifying this safely needs real multi-region credentials and
    more runway than the current submission window allows.
- The honest unblock for the demo remains operational, not architectural: request
  a `cpu-d3` AI-Jobs quota increase, or drive the offline `?demo=1` report path
  that needs no Jobs at all.

## Relationship to other ADRs

Builds directly on **ADR-009** (preset-size ladder + capacity probe). ADR-009
handles *"this preset never provisioned → try the next size"* after submission;
ADR-010 Part A handles *"this region has no quota → don't submit at all"* before
it, and Part B generalises the ladder from preset-size to region.
