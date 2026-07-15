# The Accept-then-Stall Capacity Probe + Failover Ladder

> Named-pattern deep-dive for Archon's resilient serverless job provisioning.
> This document is the canonical reference behind the README's
> [Resilient job provisioning](../README.md#resilient-job-provisioning-graceful-compute-failover)
> section and **ADR-009**. All code lives in
> [`backend/services/nebius.py`](../backend/services/nebius.py).

## The problem: a serverless job can lie to you

A Nebius Serverless AI **Job** is a *request* for compute, not a guarantee of it.
Archon's extraction and analysis pipelines each run as an on-demand CPU Job. Job
quota on Nebius is granted **per compute preset** (per `platform:preset` size), so
when the requested preset has **zero quota**, something worse than a rejection
happens: the job is *accepted*, sits in `PROVISIONING`, never allocates an
instance, and tears itself down with no clean error. Your submission returned a
job id. Nothing is coming.

This was a real incident. `cpu-d3` AI-Jobs quota was 0, every submitted job
self-destructed at provisioning with no instance and no error, and the whole
pipeline stalled **invisibly** — no exception, no 500, just a spinner that never
resolves. The failure mode is specific and worth naming:

> **Accept-then-stall** — the platform accepts a job it has no capacity to run,
> then silently strands it in `PROVISIONING`.

The pattern below turns that invisible stall into a bounded, observable,
self-healing behaviour that either finds working capacity or fails **loudly** with
an HTTP 503.

## Failure taxonomy

Every submission outcome is classified into one of four buckets. Only one of them
triggers failover.

| # | Failure mode | How Archon detects it | How Archon handles it |
|---|---|---|---|
| 1 | **Submit-rejected** — the `create` call itself raises a capacity/quota precondition (`FAILED_PRECONDITION`, `RESOURCE_EXHAUSTED`, "quota", "capacity", "unavailable", "insufficient"). | `_is_provisioning_error(exc)` matches the exception text against `_PROVISIONING_ERROR_MARKERS`. Any *other* exception (bad image, malformed spec, auth) is **not** a provisioning error. | **Fail over** to the next ladder rung. A non-provisioning exception is re-raised immediately (it would recur identically on every preset). |
| 2 | **Accepted-but-never-provisioned** — the job is accepted but *unambiguously* never reaches compute: a terminal failure (`FAILED`/`CANCELLED`/`ERROR`) with **zero instances** and never `RUNNING`, **or** a job that vanishes mid-probe (GetJob raises — silent teardown). | `_await_provisioning(service, job_id)` returns `_NEVER_PROVISIONED`. The discriminator is **instance-count + terminal-state** — never elapsed time. | Delete the never-provisioned scaffolding (`_safe_delete_job`) so nothing leaks, then **fail over** to the next rung. When the whole ladder is exhausted, raise `ComputeCapacityUnavailable` → **HTTP 503**. |
| 3 | **App-failure** — the job **reached compute** (`RUNNING` / instances present / `started_at` set) and *then* failed. | `_await_provisioning` returns `_APP_FAILURE` — `has_compute` was true at a terminal-failure state. | **No failover.** Surfaced immediately as a `RuntimeError`. A bug that recurs identically on every preset must not be retried — that would mask the bug and waste money. |
| 4 | **Still-provisioning (healthy slow start)** — the probe window elapses while the job is still in `PROVISIONING` with zero instances and **no** terminal state. Nebius Jobs legitimately take **minutes** to provision (~5 min cold start), far longer than the probe window. | `_await_provisioning` returns `_PENDING_PROVISION`. | **No failover, no delete.** Return the job as pending and **keep it** — the caller/frontend polls THIS job id to completion on the same machine. Deleting a healthy slow provision and spawning a new preset job was the days-costly bug that walked the whole ladder (CPU→GPU), recreating jobs and spawning phantom "Deleting" churn. |

The distinction between #2 and #3 is the crux for *failover vs. app-error*: **did the
job ever get compute?** If no instance was ever allocated *and* the job is in a
terminal-failure state (or vanished), it is a capacity miss worth retrying
elsewhere. If compute was allocated and the container then failed, it is an
application/config bug that every preset will reproduce.

Elapsed time never decides failover. A job merely still in `PROVISIONING` at the
deadline (#4) is **not** presumed dead — we cannot tell a healthy slow provision
from a zero-capacity stall by the clock, so we refuse to guess: it is returned as
pending and kept, never deleted, never failed over. Failover is reserved for the
unambiguous never-provisioned signals in #2 (terminal failure with zero instances,
or a vanished job) and the submit-time precondition in #1.

## Architecture

Two functions carry the pattern, both in
[`backend/services/nebius.py`](../backend/services/nebius.py):

- **`_submit_job_with_failover(name_prefix, period, default_platform, default_preset, build_spec)`**
  — the orchestrator. Walks the ladder from `_preset_ladder(...)`, submits each
  rung at most once via the injected `build_spec(platform, preset)` factory,
  classifies the outcome, and either returns the running job, re-raises an app
  error, or fails over. Shared by both `_submit_nebius_job` (extraction) and
  `_submit_nebius_analysis_job` (analysis) — DRY across both pipelines.
- **`_await_provisioning(service, job_id)`** — the probe. Polls `GetJob` for a
  bounded window and returns exactly one of `_PROVISIONED`, `_PENDING_PROVISION`
  (healthy slow start — kept and returned as pending), `_NEVER_PROVISIONED`, or
  `_APP_FAILURE`.

Supporting pieces:

| Symbol | Role |
|---|---|
| `_preset_ladder(default_platform, default_preset)` | Builds the ordered, de-duplicated `(platform, preset)` ladder. Source of truth is `JOB_PRESET_LADDER`; unset ⇒ live per-job preset first, then the verified `_DEFAULT_FALLBACK_LADDER` (`cpu-d3:8vcpu-32gb`). |
| `_parse_ladder_env()` | Defensively parses `JOB_PRESET_LADDER` (`platform:preset,...`), logging and skipping malformed entries. |
| `_is_provisioning_error(exc)` | Classifies a submit-time exception as capacity-related (`_PROVISIONING_ERROR_MARKERS`) vs. a genuine error. |
| `_safe_delete_job(service, job_id)` | Deletes never-provisioned scaffolding before the next rung so no jobs leak. |
| `ComputeCapacityUnavailable` | Raised when every rung fails to provision; the API layer maps it to **HTTP 503** with the list of presets tried. |

Tunables (all read from the environment, with safe defaults):

| Env var | Default | Meaning |
|---|---|---|
| `JOB_PRESET_LADDER` | *(unset)* | Ordered `platform:preset,...` failover ladder. Unset ⇒ live preset then `cpu-d3:8vcpu-32gb`. |
| `JOB_PROVISION_PROBE_SECS` | `90` | How long the probe watches a just-submitted job for a fast provisioning outcome before returning it as pending. Kept generous so a healthy-but-slow provision is returned and KEPT (polled to completion), never killed. |
| `JOB_PROVISION_POLL_SECS` | `5` | Poll interval inside the probe window. |

### Flow

```
submit_extraction_job / submit_analysis_job
        │
        ▼
_submit_job_with_failover(build_spec)
        │
        ├── for each (platform, preset) in _preset_ladder(...):
        │        │
        │        ├── service.create(...)  ──raises capacity error?──►  [1 submit-rejected] ► next rung
        │        │                          raises other error?     ►  re-raise (genuine bug)
        │        │
        │        ▼
        │   _await_provisioning(service, job_id)
        │        │
        │        ├── _PROVISIONED        ► return running job  (poll to completion)
        │        ├── _PENDING_PROVISION  ► [4] return SAME job as pending  (keep it, poll to completion — NO failover)
        │        ├── _APP_FAILURE        ► [3] raise RuntimeError  (NO failover)
        │        └── _NEVER_PROVISIONED  ► [2] _safe_delete_job → next rung
        │
        ▼
   ladder exhausted ► raise ComputeCapacityUnavailable ──► HTTP 503
```

## Why not just ask Nebius for capacity? (investigation findings)

Before building an empirical probe, we checked whether Nebius exposes a capacity
oracle we could query *before* submitting. It does — but not for the platform
Archon runs on.

**What exists.** The pinned SDK (`nebius==0.3.76`) ships a capacity API at
`nebius.api.nebius.capacity.v1` — `ResourceAdviceServiceClient` with
`ListResourceAdviceRequest` / `ListResourceAdviceResponse` (CLI equivalent:
`nebius capacity resource-advice list`). It returns per-`(region, fabric,
platform, preset)` availability with three allocation types (reserved /
on_demand / preemptible) and an availability level.

**The catch.** For this tenant the service returns **only GPU platforms**
(`gpu-h100`, `gpu-h200`, `gpu-l40s`, and siblings). `cpu-d3` — the *only* CPU
platform in `eu-west1` and the one every Archon Job actually runs on — **never
appears**, even with `--all`. A `cpu-d3` capacity pre-check built on this API
would be inert: it would always return "no advice" for the platform we care
about, giving a false sense of coverage while checking nothing.

**Conclusion.** Nebius exposes **no capacity oracle for CPU job presets**, so a
pre-flight check is not an option for this workload. The provisioning probe *is*
our capacity API: rather than asking whether capacity exists, we submit, watch for
a real instance within a bounded window, and treat "no instance by the deadline"
as an authoritative, empirical "no capacity here — try the next rung." This is
strictly more truthful than a GPU-only oracle could be, because it measures the
exact `(platform, preset)` Archon is about to use, at the moment it uses it.

## The GPU rung is opt-in only

The ladder accepts any `platform:preset` pair, so a `gpu-h200-sxm` rung *can* be
appended as a last-resort escape when every `cpu-d3` size is quota-blocked. It is
**off by default and intentionally absent from the default ladder**: Archon jobs
are CPU workloads (all LLM inference is remote HTTP to the Nebius Inference API),
so a GPU rung would add substantial cost for zero application-compute benefit.
The current CPU Endpoint estimate is documented in the README from Nebius's
published rates; verify current regional pricing before enabling any GPU rung.
See `.env.example` for the annotated opt-in example and cost warning.

## Reproduce it in one command

The pattern is exercised offline — no Nebius credentials, no live capacity, and
no real Job submission:

```bash
bash scripts/demo-failover.sh
```

The demo sets `JOB_PRESET_LADDER` with a deliberately-unprovisionable first rung
(one that terminally fails with zero instances — the unambiguous never-provisioned
signal), mocks the provisioning outcomes, and drives the **real**
`_submit_job_with_failover` so you can watch the live log narration fail over from
the capacity-failed rung to a working one. It is covered in CI by
`backend/tests/test_demo_failover.py`, alongside the full failover unit suite and
a real-pysdk `JobStatus` shape contract test in
`backend/tests/test_nebius_service.py`.

## See also

- **ADR-009** — the architecture decision record this pattern implements (referenced from `README.md`).
- `README.md` → *Resilient job provisioning (graceful compute failover)*.
- `.env.example` → the annotated `JOB_PRESET_LADDER` / probe tunables.
