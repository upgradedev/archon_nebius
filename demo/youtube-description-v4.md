# YouTube Upload Details — Corrected Nebius Presentation v4

## Title

Archon — Financial Document Control on Nebius Serverless AI | Technical Proof

## Description

Archon is a financial-document control prototype for structured extraction, document-type refinement, human review, one bounded payroll-linking example, and deterministic validation.

The actual workflow is explicit: extraction, classification, payroll linking, and R1–R4 run before review; the reviewer then corrects or excludes successfully extracted documents; analysis reads the approved period set. Extraction records failed-file metadata in machine-readable artifacts and logs, but the current review UI does not display it.

Payroll findings reference their supporting source files. That traceability is limited to the named validations; the build does not prove that taxes or social-security liabilities were remitted and does not provide complete report-wide lineage.

The supplier Reconciliation Agent is unit-tested against pre-structured statement entries, but the current extractors do not populate those entries. General invoice-to-payment, invoice-to-collection, duplicate/wrong-vendor payment, remittance matching, and journal export are future work.

Nebius deployment boundary:
- A CPU AI Endpoint hosts FastAPI; separate extraction and analysis AI Job packages and SDK submission are implemented.
- The bounded provisioning ladder maps e00/eu-north1, e01/eu-west1, and e03/uk-south1 to their project-local subnets. It advances only for qualifying provisioning failures, so this is not a generic high-availability claim.
- Inline subprocess execution is retained as an emergency fallback only.
- Qwen2.5-VL and Llama 3.3 are called through the Nebius Inference API.
- Object Storage is authoritative; Managed PostgreSQL is a best-effort mirror.
- Nebius Container Registry hosts the two job images; GitHub Container Registry hosts the Endpoint image.
- Firebase provides the authenticated browser edge.

Public deployment evidence:
- Endpoint deploy, PostgreSQL reachability, and BFF HTTP 200: https://github.com/upgradedev/archon_nebius/actions/runs/29419841856
- Authenticated report serving and PostgreSQL mirror trigger: https://github.com/upgradedev/archon_nebius/actions/runs/29309815367
- Official Nebius Compute quota reference: https://docs.nebius.com/compute/resources/quotas-limits
- Read-only three-project probe for Jobs access, project regions, and Compute quota rows: https://github.com/upgradedev/archon_nebius/actions/runs/29452440996
- Short three-project smoke: all 3 CreateJobRequest calls succeeded, but every Job stayed PROVISIONING with 0 instances until the 9-minute harness timed out and deleted it. The workflow is a terminal harness failure, not successful execution or a pending run: https://github.com/upgradedev/archon_nebius/actions/runs/29452734826
- Long 35-minute three-project smoke — TERMINAL WORKFLOW FAILURE: all 3 creates were accepted; each Job initially reported state 1 / PROVISIONING with 0 instances, then reached state 9 / ERROR around 30 minutes later with 0 instances and empty JobStateDetails. Cleanup deleted all 3 Jobs. This proves create acceptance followed by a pre-compute terminal error, not workload execution, and the empty details do not establish quota exhaustion or another root cause: https://github.com/upgradedev/archon_nebius/actions/runs/29453371645
- Cross-region production deployment — SUCCESS: archon-backend-r133 reached RUNNING with JOB_RUNNER_BACKEND=nebius and JOB_QUOTA_PREFLIGHT=1. The deployed NEBIUS_PROJECT_CONFIGS contained project-e00cncsmpr00e8p6knyvdq/eu-north1/vpcsubnet-e00sn2btkrs87k2re4, project-e01mmzejpr00e93rgqgf3q/eu-west1/vpcsubnet-e01x810n0mmhj19k9b, and project-e03byhh4pr00v15s7dz11p/uk-south1/vpcsubnet-e03w9xd3nbg2abq7qb. Jobs-list permission passed in all 3 projects, the Object Storage write/read/delete round-trip passed, the Firebase BFF function was updated, and the live /api/health probe returned HTTP 200: https://github.com/upgradedev/archon_nebius/actions/runs/29453848235

The production deployment proves that the live backend is configured for Nebius Jobs orchestration. The terminal long smoke proves that each configured project accepted a create request and later returned a pre-compute ERROR with no instance allocation; it does not prove workload execution or completion of an application extraction or analysis Job.

The 40-case offline evaluation reports a deterministic perfect-input downstream ceiling and a degraded sensitivity test. The 100% ceiling is not a live-Qwen extraction score; no live-extraction accuracy result is published.

TIMESTAMPS

0:00 Product boundary and operational problem
0:36 Extraction first; review before analysis
1:14 Payroll as one bounded linking example
1:51 Supplier reconciliation: exact boundary
2:28 Deployed Nebius architecture
3:16 Two pipelines separated by review
3:59 What the evaluation actually proves
4:47 Bounded cross-region AI Jobs provisioning failover
5:34 Probe evidence and smoke-run status boundary
6:13 Current proof and explicit next work

GitHub (MIT): https://github.com/upgradedev/archon_nebius

#NebiusServerlessChallenge #ServerlessAI #FinTech #Python #LLM

## Visibility

Unlisted while reviewing; public or unlisted with a shareable link if attached as optional supporting material.
