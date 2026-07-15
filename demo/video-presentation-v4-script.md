# Archon — Corrected Nebius Presentation Script v4

## 1. The operational problem

Small-business finance starts with documents that must be understood, classified, reviewed, and connected before anyone should trust a period view. Archon is a financial-document control prototype built around that workflow. It extracts structured records, lets a person decide what proceeds, links one implemented event family, and reports bounded validation findings. It supports automated entry, clear categorization, human review, and bounded cross-document controls. Accounting journals and general payment matching remain beyond this prototype.

## 2. Extraction first; review before analysis

The extraction package runs before the human review gate. It extracts, classifies, links payroll documents, applies R1 through R4, and writes documents, events, validations, and a machine-readable failed-file summary to Object Storage. The current review screen loads only documents that extracted successfully, so failed files are recorded in extraction artifacts and logs, but are not yet visible in that interface. The reviewer can correct a type or exclude a record. The approved documents then replace the period document set, and analysis reads that reviewed set.

## 3. Payroll is one bounded linking example

Payroll demonstrates the implemented event-linking pattern. The extraction `EventLinker` groups a bank confirmation, payroll register, and payslips by company and document month. Four deterministic checks compare bank and payslip totals, an employer-cost ratio, the bank document date, and headcount. Validation findings carry the relevant source-file names, which is the traceability implemented today. These checks do not verify that payroll taxes or social-security liabilities were remitted, and they do not establish general report-wide lineage for every displayed number.

## 4. Supplier reconciliation — exact boundary

The repository includes a unit-tested supplier `ReconciliationAgent`. When it receives pre-structured statement entries, it can identify invoice numbers missing from the uploaded set, unmatched uploads, and a balance difference. The current image, PDF, and DOCX extraction mappings do not populate those statement entries, so this component is not an end-to-end user flow in the submitted build. It is also not a bank-payment matcher. Invoice settlement, collections, duplicates, wrong-vendor payments, and tax or contribution remittances remain future event families.

## 5. The deployed Nebius architecture

A Nebius CPU AI Endpoint hosts the FastAPI backend. Extraction and analysis are packaged as separate on-demand AI Job entry points, but this tenant currently has zero CPU Jobs quota. The live Endpoint therefore runs those same packages as isolated subprocesses. Qwen2.5-VL performs document extraction and Llama 3.3 produces optional narration through the Nebius Inference API. Object Storage is authoritative for raw, extracted, and report artifacts; Managed PostgreSQL is a best-effort relational mirror. Nebius Container Registry hosts the two job images, while the live Endpoint image is pulled from GitHub Container Registry. Firebase supplies the authenticated browser edge.

## 6. Two pipelines separated by review

The extraction and analysis packages are separated by the review boundary. Extraction creates an event and validation artifact from the successful pre-review documents. The browser then sends back the approved period set. Analysis loads those reviewed documents, performs its own classification, builds the current P&L and cash-flow views, re-runs the payroll validations, builds employee summaries, calls the supplier component when structured inputs exist, and finally requests narration. The language models operate at the unstructured edges. Python performs the arithmetic and controls, and a narration failure falls back to a deterministic summary.

## 7. What the evaluation actually proves

The offline evaluation harness imports the real downstream agents and scores 40 labelled synthetic payroll cases. With deterministic perfect structured input, classification, selected-field, validation, and payroll-fusion accuracy reach 100%. A deliberately degraded extractor drops classification to 74.29%, selected fields to 77.62%, validation outcomes to 66.87%, and fusion to 54.05%. The harness also moved two formerly dormant rules from 0/37 to 37/37 applicable cases. The 100% result is a downstream ceiling, not a live Qwen vision score; no live-extraction accuracy result is published in this submission.

## 8. Exact AI Jobs failover behavior

The failover rule is narrower than a timeout. If job creation is rejected for quota or capacity, Archon tries the next configured project and preset. If a job reaches a terminal failure with zero instances, or vanishes while provisioning, Archon cleans up that never-provisioned job and advances. If the bounded probe ends while the job is still pending, it keeps that same job and continues polling; elapsed time alone never triggers failover or a duplicate submission. If compute was provisioned and the application then fails, Archon surfaces the application error without retrying another preset. This logic is built and tested, but the current live product uses the inline subprocess path because tenant CPU Jobs quota is zero.

## 9. Public deployment evidence

The deployment evidence is public. [GitHub Actions deployment run 29419841856](https://github.com/upgradedev/archon_nebius/actions/runs/29419841856) shows the Nebius CPU Endpoint reaching `RUNNING` with the inline runner, PostgreSQL reachable through its private endpoint, and the Firebase BFF health route returning HTTP 200. A separate [PostgreSQL seed run 29309815367](https://github.com/upgradedev/archon_nebius/actions/runs/29309815367) exercises authenticated report serving and triggers the PostgreSQL read-model mirror. These logs prove the deployed Endpoint and state path. They do not claim that a CPU AI Job provisioned; none did under the tenant's zero Jobs quota.

## 10. Current proof and explicit next work

The submitted proof is deliberately bounded: mixed-file extraction, structured records, deterministic type refinement, human review of successfully extracted documents, payroll linking, four named checks with source-file references, reproducible downstream evaluation, and a live Nebius Endpoint using the inline fallback. The next work is equally explicit: surface failed-file summaries in the review interface, wire supplier-statement extraction, add invoice-to-payment and invoice-to-collection events, verify tax and contribution remittances, and integrate with accounting journals. That boundary is the honest Archon story for this challenge.
