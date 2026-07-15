# ADR-010 — Compute-quota routing and bounded cross-region Job provisioning

**Date:** 2026-07-13

**Updated:** 2026-07-16
**Status:** Implemented; production deployment and terminal long-smoke result verified

## Context

Archon's extraction and analysis packages are CPU Serverless AI Jobs. The three
available projects are in different regions and require project-local subnets:

| Project | Region | Subnet |
|---|---|---|
| `project-e00cncsmpr00e8p6knyvdq` | `eu-north1` | `vpcsubnet-e00sn2btkrs87k2re4` |
| `project-e01mmzejpr00e93rgqgf3q` | `eu-west1` | `vpcsubnet-e01x810n0mmhj19k9b` |
| `project-e03byhh4pr00v15s7dz11p` | `uk-south1` | `vpcsubnet-e03w9xd3nbg2abq7qb` |

A project-ID-only ladder was insufficient: a Job submitted under one project
could not safely inherit the Endpoint project's `eu-west1` region and subnet.
Likewise, matching quota rows heuristically on `job` or `cpu-d3` was unsupported.
Nebius documents that Serverless AI workloads consume underlying
[Compute quotas](https://docs.nebius.com/compute/resources/quotas-limits), and the
real project rows are `compute.instance.count` and
`compute.instance.non-gpu.vcpu`.

The [read-only probe run](https://github.com/upgradedev/archon_nebius/actions/runs/29452440996)
verified that the runtime service account can list Jobs and quota allowances in
all three projects. It also recorded each project's region and the two real
Compute quota rows. Every observed `spec.limit` was omitted (`None`), which is a
provider-default/unknown allowance, not evidence of a zero limit. The probe did
not create compute and is not proof that an AI Job completed.

## Decision

### 1. Project-local routing configuration

`NEBIUS_PROJECT_CONFIGS` is the source of truth for cross-region placement. Its
format is an ordered comma-separated list of `project=region=subnet` entries:

```text
project-e00cncsmpr00e8p6knyvdq=eu-north1=vpcsubnet-e00sn2btkrs87k2re4,
project-e01mmzejpr00e93rgqgf3q=eu-west1=vpcsubnet-e01x810n0mmhj19k9b,
project-e03byhh4pr00v15s7dz11p=uk-south1=vpcsubnet-e03w9xd3nbg2abq7qb
```

The line breaks above are for readability; the environment value is a single
line. Each JobSpec receives the selected project's subnet. When the variable is
absent, the legacy `NEBIUS_PROJECT_ID[_LADDER]`, `NEBIUS_REGION`, and
`NEBIUS_SUBNET_ID` contract preserves single-region compatibility.

The backend Endpoint, authoritative Object Storage, registry, and PostgreSQL
remain anchored in the primary e01/`eu-west1` deployment. A Job placement does
not infer its region or subnet from that Endpoint.

### 2. Project-specific Compute quota selector

When `JOB_QUOTA_PREFLIGHT` is enabled, the runner lists quota allowances with the
candidate **project** as `parent_id`; it never substitutes the tenant and thereby
returns the same quota view for every project. For the candidate's own region it
evaluates:

- `compute.instance.count`
- `compute.instance.non-gpu.vcpu`

An explicit limit is reduced by current `status.usage`. A candidate is confirmed
exhausted if either required allowance has no remaining headroom. An omitted
limit, missing row, SDK/API error, or ambiguous duplicate is `unknown` and fails
open. Available candidates are ordered before unknown candidates; only confirmed
exhaustion removes a candidate.

The selector is a quota signal, not a general capacity oracle. It does not claim
that a positive or default allowance guarantees immediate provisioning.

### 3. Bounded project × preset provisioning failover

After project ordering, the existing `JOB_PRESET_LADDER` applies within each
project. Every project × preset candidate is tried at most once. The runner
advances only on an unambiguous never-provisioned signal:

- create rejected for provisioning/quota/capacity;
- terminal failure with zero instances and no evidence of having run; or
- a Job that vanishes during the bounded provisioning probe.

A Job still provisioning when the probe ends is retained and returned for
polling. Elapsed time alone does not delete it or create a duplicate. If compute
was allocated and the application then fails, that application error is surfaced
without replaying it in another region.

This policy is **bounded cross-region provisioning failover**, not generic high
availability. It does not promise uninterrupted service, automatic replay of
application failures, or regional data replication.

### 4. Inline execution is emergency fallback only

`JOB_RUNNER_BACKEND=inline` remains a break-glass continuity option. It invokes
the same extraction and analysis entrypoints as isolated subprocesses inside the
Endpoint and preserves their Object Storage/status contracts. Its existence is
not evidence that an AI Job ran. Production run 29453848235 proves that r133 uses
`JOB_RUNNER_BACKEND=nebius`; inline remains an inactive, operator-selected
break-glass option.

## Evidence boundary

- [Probe run 29452440996](https://github.com/upgradedev/archon_nebius/actions/runs/29452440996)
  is read-only evidence for project access, regions, quota-row identity, limits,
  and usage.
- [Short smoke run 29452734826](https://github.com/upgradedev/archon_nebius/actions/runs/29452734826)
  is a terminal harness failure, not a pending run. All three
  `CreateJobRequest` calls succeeded, one for each configured placement. Every
  Job then remained `PROVISIONING` with zero instances until the nine-minute
  harness timed out and deleted it. This proves API acceptance of the three
  placement requests; it does **not** prove provisioning or execution.
- [Long smoke run 29453371645](https://github.com/upgradedev/archon_nebius/actions/runs/29453371645)
  is a terminal workflow failure. All three `CreateJobRequest` calls succeeded.
  Each Job initially reported state 1 (`PROVISIONING`) with zero instances. At
  around 30 minutes, each transitioned to state 9 (`ERROR`), still with zero
  instances and empty `JobStateDetails`. Cleanup deleted all three Jobs, after
  which the workflow exited with failure. This proves create acceptance followed
  by a pre-compute terminal error, not workload execution. The empty details do
  not establish quota exhaustion, capacity failure, or another root cause.
- [Production deployment run 29453848235](https://github.com/upgradedev/archon_nebius/actions/runs/29453848235)
  completed successfully. The new `archon-backend-r133` Endpoint reached
  `RUNNING` with `JOB_RUNNER_BACKEND=nebius`, `JOB_QUOTA_PREFLIGHT=1`, and all
  three project/region/subnet configurations in the table above. The runtime
  service account passed Jobs-list permission checks in all three projects; the
  Object Storage write/read/delete round-trip passed; the Firebase BFF function
  was updated; and the live `/api/health` probe returned HTTP 200.
- [Single live-app extraction smoke 29456062145](https://github.com/upgradedev/archon_nebius/actions/runs/29456062145)
  sent exactly one authenticated upload and one extraction request through the
  public Firebase BFF. The API returned `aijob-e00gyxyn1n4bygw91n`, routed to
  `project-e00cncsmpr00e8p6knyvdq`, with `pending` status. This proves live
  Jobs-mode dispatch through the deployed application, not instance allocation
  or workload completion.
- The deployment proves that the live Archon backend activated Nebius Jobs-mode
  orchestration, quota preflight, and the configured placement ladder. It does
  **not** prove completion of an application extraction or analysis Job.

## Consequences

- Cross-region placement is explicit and auditable instead of inferred from the
  primary Endpoint.
- Default/unknown provider quota is no longer misreported as a hard zero.
- The runtime service account must retain Jobs and subnet access in all three
  projects and registry-read access for the Job images.
- Jobs outside `eu-west1` read the authoritative Object Storage remotely, so
  cross-region latency and transfer charges may apply. Jobs do not write directly
  to PostgreSQL; the eu-west1 Endpoint continues to materialize that read model.
- Operators can return to emergency inline execution with one variable if Job
  placement is unavailable, without changing agent code or artifact contracts.

## Relationship to ADR-009

ADR-009 defines the never-provisioned versus application-failure taxonomy and the
preset ladder. ADR-010 adds project-specific Compute-quota ordering and the
project→region→subnet dimension while retaining ADR-009's bounded, no-duplicate
semantics.
