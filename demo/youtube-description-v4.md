# YouTube Upload Details — Corrected Nebius Presentation v4

## Title

Archon — Financial Document Control on Nebius Serverless AI | Technical Proof

## Description

Archon is a financial-document control prototype for structured entry, document classification, human review, payroll evidence linking, and deterministic validation. It is not a “hidden cost” detector.

The workflow is explicit: extraction, classification, payroll linking, and rules R1–R4 run before review. The reviewer can correct or exclude successfully extracted records; analysis then reads the approved period set. Failed-file metadata is written to machine-readable artifacts and logs, although the current review UI does not display it.

Implemented controls link a payroll register, bank confirmation, and payslips, then check net totals, the employer-cost/net ratio, payment date, and headcount. Findings cite supporting source files. The build does not verify separate tax or social-security remittances and does not provide complete report-wide lineage.

The supplier Reconciliation Agent is unit-tested for pre-structured statement entries, but raw statement extraction is not wired end to end. General invoice-to-payment, invoice-to-collection, duplicate/wrong-vendor payment, remittance matching, and journal export remain future work.

NEBIUS ARCHITECTURE
- A CPU AI Endpoint hosts FastAPI.
- Separate extraction and analysis AI Job packages use bounded project-local routes: e00/eu-north1, e01/eu-west1, and e03/uk-south1.
- Production revision r133 uses JOB_RUNNER_BACKEND=nebius and quota preflight. Inline execution is an inactive emergency fallback only.
- Qwen2.5-VL and Llama 3.3 use the Nebius Inference API.
- Object Storage is authoritative; Managed PostgreSQL is a best-effort mirror.
- Nebius Container Registry holds the Job images; Firebase provides the authenticated browser edge.

PUBLIC EVIDENCE
- Production deployment r133 — SUCCESS: https://github.com/upgradedev/archon_nebius/actions/runs/29453848235
- Single live-app extraction smoke — SUCCESS: the authenticated public app returned aijob-e00gyxyn1n4bygw91n through project e00 with pending status: https://github.com/upgradedev/archon_nebius/actions/runs/29456062145
- Read-only three-project Jobs/quota probe: https://github.com/upgradedev/archon_nebius/actions/runs/29452440996
- Short three-project smoke: 3/3 creates accepted; all stayed PROVISIONING with zero instances until the harness timeout: https://github.com/upgradedev/archon_nebius/actions/runs/29452734826
- Long three-project smoke: 3/3 creates accepted; all later entered ERROR with zero instances and empty details; cleanup succeeded: https://github.com/upgradedev/archon_nebius/actions/runs/29453371645

The production deployment and live-app smoke prove that the public application dispatches through Nebius Jobs orchestration. They do not prove instance allocation or completion of an application extraction or analysis Job. Empty Job details do not establish quota exhaustion, capacity failure, or another root cause.

The 40-case offline evaluation measures the real deterministic downstream agents. Its 100% perfect-input ceiling is not a live-Qwen extraction score; no live-extraction accuracy claim is published.

Live demo: https://archon-pnl.web.app/?demo=1
DEV article: https://dev.to/efousekis/building-archon-from-financial-documents-to-controlled-records-on-nebius-serverless-ai-8g6
GitHub (MIT): https://github.com/upgradedev/archon_nebius

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

#NebiusServerlessChallenge #ServerlessAI #FinTech #Python #LLM

## Visibility

Unlisted while reviewing; public or unlisted with a shareable link if attached as optional supporting material.
