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

A Nebius CPU AI Endpoint hosts the FastAPI backend. Production revision r133 is configured with `JOB_RUNNER_BACKEND=nebius`, quota preflight, and three explicit project-local routes: e00 in eu-north1, e01 in eu-west1, and e03 in uk-south1. Separate extraction and analysis AI Job packages are the configured on-demand submission path; inline subprocess execution remains an inactive emergency option. Qwen2.5-VL performs document extraction and Llama 3.3 produces optional narration through the Nebius Inference API. Object Storage is authoritative for raw, extracted, and report artifacts; Managed PostgreSQL is a best-effort relational mirror. Nebius Container Registry hosts the two Job images, GitHub Container Registry hosts the Endpoint image, and Firebase supplies the authenticated browser edge.

## 6. Two pipelines separated by review

The extraction and analysis packages are separated by the review boundary. Extraction creates an event and validation artifact from the successful pre-review documents. The browser then sends back the approved period set. Analysis loads those reviewed documents, performs its own classification, builds the current P&L and cash-flow views, re-runs the payroll validations, builds employee summaries, calls the supplier component when structured inputs exist, and finally requests narration. The language models operate at the unstructured edges. Python performs the arithmetic and controls, and a narration failure falls back to a deterministic summary.

## 7. What the evaluation actually proves

The offline evaluation harness imports the real downstream agents and scores 40 labelled synthetic payroll cases. With deterministic perfect structured input, classification, selected-field, validation, and payroll-fusion accuracy reach 100%. A deliberately degraded extractor drops classification to 74.29%, selected fields to 77.62%, validation outcomes to 66.87%, and fusion to 54.05%. The harness also moved two formerly dormant rules from 0/37 to 37/37 applicable cases. The 100% result is a downstream ceiling, not a live Qwen vision score; no live-extraction accuracy result is published in this submission.

## 8. Exact AI Jobs failover behavior

The failover rule is narrower than a timeout. Each project carries its own region and subnet. The quota selector reads the real Compute allowance rows and treats an omitted provider limit as unknown, not zero. An explicit qualifying create rejection, or a terminal or vanished Job that provably never received an instance, may advance to the next configured project and preset. If the bounded probe ends while a Job is still provisioning, Archon keeps that Job; elapsed time alone never triggers a duplicate. If compute was allocated and application code then failed, the failure is surfaced without cross-region replay. This is bounded provisioning failover, not generic high availability.

## 9. Public deployment evidence

The deployment evidence is public. [Production run 29453848235](https://github.com/upgradedev/archon_nebius/actions/runs/29453848235) created revision r133 in `RUNNING` with the Nebius Jobs backend, quota preflight, all three project-region-subnet tuples, Jobs-list permission in all three projects, an Object Storage round-trip, an updated Firebase BFF, and HTTP 200 from the public health route. The [read-only probe](https://github.com/upgradedev/archon_nebius/actions/runs/29452440996) verified Jobs and quota access. In the terminal [35-minute smoke](https://github.com/upgradedev/archon_nebius/actions/runs/29453371645), all three create requests were accepted, then each Job moved from `PROVISIONING` to `ERROR` with zero instances and empty details. Cleanup succeeded. That proves submission acceptance followed by pre-compute failure, not workload execution, and it does not identify quota or capacity as the root cause.

## 10. Current proof and explicit next work

The submitted proof is deliberately bounded: mixed-file extraction, structured records, deterministic type refinement, human review of successfully extracted documents, payroll linking, four named checks with source-file references, reproducible downstream evaluation, and a live Nebius Endpoint configured for the cross-region AI Jobs runner. No completed application extraction or analysis Job is claimed. The next work is equally explicit: surface failed-file summaries in the review interface, wire supplier-statement extraction, add invoice-to-payment and invoice-to-collection events, verify tax and contribution remittances, and integrate with accounting journals. That boundary is the honest Archon story for this challenge.
