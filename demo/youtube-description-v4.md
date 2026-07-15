# YouTube Upload Details — Corrected Nebius Presentation v4

## Title

Archon — Financial Document Control on Nebius Serverless AI | Technical Proof

## Description

Archon is a financial-document control prototype for structured extraction, document-type refinement, human review, one bounded payroll-linking example, and deterministic validation.

The actual workflow is explicit: extraction, classification, payroll linking, and R1–R4 run before review; the reviewer then corrects or excludes successfully extracted documents; analysis reads the approved period set. Extraction records failed-file metadata in machine-readable artifacts and logs, but the current review UI does not display it.

Payroll findings reference their supporting source files. That traceability is limited to the named validations; the build does not prove that taxes or social-security liabilities were remitted and does not provide complete report-wide lineage.

The supplier Reconciliation Agent is unit-tested against pre-structured statement entries, but the current extractors do not populate those entries. General invoice-to-payment, invoice-to-collection, duplicate/wrong-vendor payment, remittance matching, and journal export are future work.

Nebius deployment boundary:
- A CPU AI Endpoint hosts FastAPI and currently executes extraction and analysis as isolated subprocesses because tenant CPU AI-Jobs quota is zero.
- Separate extraction and analysis AI Job packages, SDK submission, and exact provisioning failover are built and tested; no successful CPU AI Job execution is claimed.
- Qwen2.5-VL and Llama 3.3 are called through the Nebius Inference API.
- Object Storage is authoritative; Managed PostgreSQL is a best-effort mirror.
- Nebius Container Registry hosts the two job images; GitHub Container Registry hosts the live Endpoint image.
- Firebase provides the authenticated browser edge.

Public deployment evidence:
- Endpoint deploy, inline runner, PostgreSQL reachability, and BFF HTTP 200: https://github.com/upgradedev/archon_nebius/actions/runs/29419841856
- Authenticated report serving and PostgreSQL mirror trigger: https://github.com/upgradedev/archon_nebius/actions/runs/29309815367

The 40-case offline evaluation reports a deterministic perfect-input downstream ceiling and a degraded sensitivity test. The 100% ceiling is not a live-Qwen extraction score; no live-extraction accuracy result is published.

TIMESTAMPS

0:00 Product boundary and operational problem
0:36 Extraction first; review before analysis
1:14 Payroll as one bounded linking example
1:51 Supplier reconciliation: exact boundary
2:28 Deployed Nebius architecture
3:16 Two pipelines separated by review
3:59 What the evaluation actually proves
4:47 Exact AI Jobs failover behavior
5:34 Public deployment evidence
6:13 Current proof and explicit next work

GitHub (MIT): https://github.com/upgradedev/archon_nebius

#NebiusServerlessChallenge #ServerlessAI #FinTech #Python #LLM

## Visibility

Unlisted while reviewing; public or unlisted with a shareable link if attached as optional supporting material.
