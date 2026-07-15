# Building Archon: From Financial Documents to Controlled Records on Nebius Serverless AI

*Automated extraction and classification, human review, document linking, and deterministic completeness checks for small-business finance*

*#NebiusServerlessChallenge · #ServerlessAI · #FinTech · #LLM*

---

Small-business finance does not start with a dashboard. It starts with a folder full of documents that somebody must understand and enter correctly: purchase and sales invoices, expense receipts, payroll registers, bank confirmations, payslips, and supplier statements.

The operational questions are simple to ask and expensive to answer manually:

- What is this document, and where does it belong?
- Is it a supplier invoice or a sales invoice?
- Was every expected document actually received and recorded?
- Which documents describe the same financial event?
- Does a payment or collection have supporting evidence?
- For payroll, do the register, the bank confirmation, and the payslips agree?

**Archon** is built around that control loop. It turns uploaded financial documents into structured, classified, reviewable records; links documents that describe the same event; and runs explicit checks before producing a period financial view. The goal is to make financial entry and control faster, clearer, and auditable.

The current build proves that architecture with two bounded control paths: automated document processing with a human review gate, and payroll-event linking with deterministic validation. It also contains a supplier-statement reconciliation component for structured statement entries. General invoice-to-bank-payment matching, collections matching, duplicate-payment detection, and tax-remittance verification are the next extensions of the same model, not claims about what this version already does.

> **Architecture diagram:** the complete component graph is also available in the [public repository](https://github.com/upgradedev/archon_nebius#architecture). AI Jobs are the primary execution architecture. A separate inline subprocess runner remains an operator-selected emergency fallback; it is not the current-path claim and is not evidence that an AI Job ran.

![Archon architecture on Nebius Serverless AI](https://raw.githubusercontent.com/upgradedev/archon_nebius/master/demo/article-figures/png/fig-1-architecture.png)

## The product loop: read, classify, review, record, control

Archon begins with mixed files rather than pre-cleaned rows. The extraction pipeline accepts PDFs, DOCX files, images, TIFFs, and scanned PDFs. Digital documents take the text path. Scanned and image-based documents go through Qwen2.5-VL-72B on the Nebius Inference API.

The result is a structured record with fields such as document type, date, supplier, recipient, tax identifier, currency, invoice number, VAT, totals, and line items. Payroll documents add purpose-specific fields such as employee count, gross pay, net pay, and employer cost.

Extraction is followed by deterministic classification. This second pass matters because an LLM can read a document correctly and still assign the wrong accounting type. `ClassifierAgent` refines ambiguous results using domain rules, keeping obvious classification errors out of downstream calculations.

The user then sees the successfully extracted documents before analysis. They can correct the type, exclude an unrelated file, and confirm the set that should proceed. Archon also checks whether a document appears to belong to the configured company by name or tax identifier.

There is an important current limitation around failed files. During extraction, Archon records each failed filename and reason inside the per-upload `documents.json` artifact in Object Storage and writes the failure to the job log. The current review API and UI do not expose that failure list, and confirming the reviewed set replaces the per-upload document artifact without carrying the failure metadata forward. Failures are therefore recorded during processing, but they are not yet visible to the reviewer in the product. Surfacing and preserving them through review is required before this can be described as a closed failure-handling loop.

That review gate is deliberate. Automation should remove repetitive entry work without removing control from the person responsible for the books.

![Archon financial document control loop](https://raw.githubusercontent.com/upgradedev/archon_nebius/master/demo/article-figures/png/fig-2-control-loop.png)

```python
# jobs/extraction/agents/classifier.py
def run(docs):
    for doc in docs:
        if doc.doc_type in (DocType.UNKNOWN, DocType.PAYROLL):
            doc.doc_type = _infer_type(doc)
    return docs
```

After approval, Object Storage holds the authoritative raw and structured artifacts. Managed PostgreSQL provides a relational read model for documents, payroll events, employees, and validation results. The database mirror is intentionally best-effort: a temporary database problem must not make an already-produced report disappear.

## Linking documents that describe one event

Classification answers “what is this?” Linking answers “what does it belong with?”

Payroll is a useful worked example because a single payroll run produces several documents with different roles:

- The bank confirmation records the net amount transferred to employees.
- The payroll register records gross pay, employer contributions, employee count, and the full employer cost.
- Individual payslips explain the employee-level amounts.

These are complementary records for different parts of the same event, not competing versions of one number. Archon’s `EventLinkerAgent` groups them by company and period into a `PayrollEvent`. The cash-flow view reads the bank movement; the management expense view reads the register; validation checks whether the supporting records agree.

![Payroll event linking across bank confirmation, payroll register, and payslips](https://raw.githubusercontent.com/upgradedev/archon_nebius/master/demo/article-figures/png/fig-2-payroll-gap.png)

```python
# jobs/extraction/agents/event_linker.py
def _build_event(company, period, docs):
    bank = _pick_one(docs, DocType.BANK_CONFIRMATION)
    register = _pick_one(docs, DocType.PAYROLL_REGISTER)
    payslips = [d for d in docs if d.doc_type == DocType.PAYSLIP]

    return PayrollEvent(
        period=period,
        company_name=company or None,
        bank_confirmation=bank,
        payroll_register=register,
        payslips=payslips,
        is_complete=bool(bank and register and payslips),
    )
```

Four named rules then check the linked evidence:

- **R1:** bank net approximately equals the sum of payslip nets, within ±2%.
- **R2:** employer cost divided by net pay falls inside an explicit expected band.
- **R3:** the bank-confirmation date is not later than the end of the payroll period.
- **R4:** register headcount equals the number of payslips.

Each result cites the rule, the compared values, and the source files. The output is not “the AI thinks something looks suspicious.” It is a control that a reviewer can reproduce by hand.

The broader product direction follows the same pattern. A supplier invoice should connect to its settlement evidence. A sales invoice should connect to its collection. A bank movement should be explainable by a document or obligation. Taxes and social-security liabilities should connect to their remittances. Those links are the natural next event families; the submitted build does not pretend they are already complete.

## Supplier completeness: the precise current boundary

Archon includes a unit-tested `ReconciliationAgent` that compares pre-structured entries from a supplier statement with the invoice numbers and totals present in the system. Given those fields, it can report statement invoices that are missing from the uploaded set, uploaded invoices absent from the statement, and a balance discrepancy.

That is a document-completeness component, not yet a bank-payment matcher. It is invoked by the analysis pipeline when structured statement data is present, but the current extraction prompt does not request `statement_entries`, `statement_balance`, or `statement_overdue`, and the review UI does not collect them. The component is therefore tested at the analysis boundary but is not wired end to end from a raw supplier statement through extraction and review. “This bank payment settled that invoice” is separate roadmap work.

This distinction is also why Archon keeps supplier statements out of P&L and cash-flow arithmetic. A statement is reference evidence. Counting it as an expense would duplicate the invoices it lists.

## Why Nebius Serverless AI fits the workflow

Financial-document processing is bursty. A business may upload a monthly batch, process it, inspect the results, and then do nothing for days or weeks. Keeping a dedicated GPU online for that pattern would be wasteful.

Archon separates orchestration from batch work:

- A **CPU AI Endpoint** hosts the FastAPI backend and the upload, review, job-status, analysis, and report APIs.
- An **extraction AI Job** is the configured primary on-demand submission path for processing an uploaded batch and writing structured artifacts.
- An **analysis AI Job** is the configured primary on-demand submission path for reading approved records, running the financial agents, and writing the report.
- The **Nebius Inference API** serves Qwen2.5-VL-72B for vision extraction and Llama-3.3-70B for the executive narrative.
- **Object Storage** and **Managed PostgreSQL** provide durable artifacts and a relational read model.
- **Nebius Container Registry** holds the extraction and analysis Job images. The Endpoint backend image is pulled from GitHub Container Registry.

The GPU lives in the managed inference layer rather than in Archon’s containers. The extraction and analysis packages remain CPU-only whether they run as Jobs or through the emergency fallback below.

![Why Nebius Serverless AI fits the bursty workload](https://raw.githubusercontent.com/upgradedev/archon_nebius/master/demo/article-figures/png/fig-4-cost-model.png)

The Jobs runner implements bounded cross-region provisioning failover across three project-local placements: `project-e00cncsmpr00e8p6knyvdq` in `eu-north1` on `vpcsubnet-e00sn2btkrs87k2re4`; `project-e01mmzejpr00e93rgqgf3q` in `eu-west1` on `vpcsubnet-e01x810n0mmhj19k9b`; and `project-e03byhh4pr00v15s7dz11p` in `uk-south1` on `vpcsubnet-e03w9xd3nbg2abq7qb`. This is not generic high availability. It handles provisioning placement only, keeps a slow-but-pending Job instead of duplicating it, and does not replay an application that failed after receiving compute.

`JOB_RUNNER_BACKEND=inline` remains an explicit emergency option. It runs the same two entrypoints as isolated subprocesses inside the CPU Endpoint and preserves the Object Storage and status contracts, but its presence neither changes the primary AI Jobs architecture nor proves live Job execution.

The React frontend and a thin BFF run on Firebase for public hosting, authentication, and browser-edge TLS. The precise deployment claim is therefore: **Nebius runs the domain backend, job design, inference, storage, registry, and financial data services; Firebase provides the public browser edge.**

## Two single-responsibility pipelines

![Archon extraction and analysis pipelines](https://raw.githubusercontent.com/upgradedev/archon_nebius/master/demo/article-figures/png/fig-3-pipeline.png)

The extraction package has four stages:

1. `ExtractorAgent` routes each file to text or vision extraction and emits structured fields.
2. `ClassifierAgent` refines the document type deterministically.
3. `EventLinkerAgent` groups documents that describe the same payroll event.
4. `ValidatorAgent` applies the named cross-document rules.

The analysis package has seven stages: classification, P&L aggregation, cash-flow construction, validation, employee analytics, supplier-statement reconciliation, and narrative generation.

These are the same packages in both execution modes. The primary runner is configured to submit them as two on-demand Nebius AI Jobs; the emergency runner executes them as isolated subprocesses inside the Nebius AI Endpoint. The execution boundary changes; the agents and artifact contracts do not.

Small agents are not cosmetic. They make each responsibility independently testable. A failed extraction remains an extraction problem; a classification error does not become an unexplained reporting error; and a validation rule can be measured separately from the figures it checks.

## Deterministic accounting, bounded model use

Archon does not ask a language model to calculate the financial totals. P&L figures and validation results are produced by Python arithmetic and explicit rules. The model reads messy documents and writes a narrative from already-computed metrics.

```python
def build_pnl(period, docs):
    revenue = sum(d.total_amount for d in docs if d.doc_type in REVENUE_DOC_TYPES)
    expenses = _compute_expenses(docs)
    return MonthlyPnL(
        period=period,
        revenue=round(revenue, 2),
        expenses=round(expenses, 2),
        netProfit=round(revenue - expenses, 2),
    )
```

If narrative generation fails, the report still exists. The language model is useful at the unstructured edges of the workflow; it is not the ledger.

The current cash-flow output is a provisional document-derived view, not a bank-reconciled cash statement. Payroll cash uses the actual `bank_confirmation` transfer, but sales invoices are assumed collected and purchase invoices or expense documents are assumed paid. Until general payment and collection linking is implemented, those invoice-derived inflows and outflows must not be presented as verified bank movements.

## Measuring the implemented controls

The repository includes an offline evaluation harness built around 40 labelled synthetic payroll cases. It imports the real `ClassifierAgent`, `EventLinkerAgent`, `ValidatorAgent`, and `PnLAgent` rather than reimplementing them inside the test.

Under a deterministic perfect-extraction ceiling, classification, selected-field accuracy, and payroll-fusion accuracy reach 100%. A deliberately degraded extractor drops classification to 74.29%, field accuracy to 77.62%, and fusion accuracy to 54.05%. That drop is useful: small field errors compound when records are linked.

The 100% figure is not a claim that live Qwen extraction is perfect. It is a ceiling test for the downstream agents given correct structured fields. Keeping that distinction explicit makes the benchmark useful rather than promotional.

The harness also found a real defect. R2 and R4 initially fired 0 out of 37 applicable cases because the extraction prompt did not request the register fields those rules consumed. After the fields were added and mapped, the same tests measured 37 out of 37. That before-and-after result is exactly what an evaluation harness should produce: evidence that a control is active, not just code that looks plausible.

```bash
python eval/generate_corpus.py --out corpus/full --n 40 --seed 7
python eval/evaluate.py --corpus eval/corpus/full --out eval/RESULTS_full.json
```

The benchmark runs offline with no API key and only `pydantic`. The public repository includes the generated results, tests, and reproduction commands.

## An operational lesson from AI Jobs

The most useful Serverless engineering lesson came from a failure mode. A Nebius AI Job can be accepted, remain `PROVISIONING` with zero instances, and later enter `ERROR`; acceptance alone does not prove provisioning or execution.

Archon wraps job submission in a bounded provisioning-state probe. It distinguishes:

1. creation explicitly rejected for a qualifying provisioning, quota, or capacity error,
2. accepted but never provisioned,
3. an application that reached compute and then failed.

An explicit qualifying create rejection, or a terminal/vanished Job that provably never received an instance, advances to the next bounded project × preset candidate. If an accepted Job is still provisioning when the observation window ends, Archon keeps and returns that pending Job rather than deleting it or creating a duplicate. A Job that reached compute and then failed is surfaced as an application failure, not retried elsewhere.

Nebius documents that Serverless AI Jobs consume the underlying [Compute quotas](https://docs.nebius.com/compute/resources/quotas-limits). Archon therefore queries `compute.instance.count` and `compute.instance.non-gpu.vcpu` for each candidate's own region, accounts for current usage when a limit is explicit, treats an omitted provider-default limit as unknown rather than zero, and fails open on uncertainty. The [read-only probe run](https://github.com/upgradedev/archon_nebius/actions/runs/29452440996) verified Jobs-list and quota access, the three project regions, and the real quota-row names. Project-local subnet IDs come from the explicit routing configuration. The [short three-project smoke](https://github.com/upgradedev/archon_nebius/actions/runs/29452734826) then submitted against each tuple: all three `CreateJobRequest` calls succeeded, but every Job remained `PROVISIONING` with zero instances until the nine-minute harness timed out and deleted it. The workflow's terminal failure is therefore a harness timeout, not successful Job execution and not a pending result. The terminal [35-minute smoke](https://github.com/upgradedev/archon_nebius/actions/runs/29453371645) also accepted all three creates. Each Job initially reported state 1 (`PROVISIONING`) with zero instances; around 30 minutes later, each reported state 9 (`ERROR`), still with zero instances and empty `JobStateDetails`. Cleanup deleted all three Jobs, and the workflow concluded with failure. This proves create acceptance followed by a pre-compute terminal error, not workload execution. The empty details do not identify quota exhaustion, capacity, or another root cause.

That evidence boundary matters. Reproducible engineering includes both what a probe proves and what it does not.

## Try the build

The public repository is MIT licensed. A fresh local run needs Docker, Python, `curl`, `jq`, and a Nebius Inference API key. First generate the synthetic PDFs and start the stack:

```bash
git clone https://github.com/upgradedev/archon_nebius
cd archon_nebius
cp .env.example .env
# Edit .env and replace the NEBIUS_INFERENCE_API_KEY placeholder.
python -m pip install reportlab
python scripts/generate-sample-data.py
docker compose up --build
```

Then, in a second terminal while the stack is running:

```bash
cd archon_nebius
bash scripts/test-pipeline.sh
```

The [live demo](https://archon-pnl.web.app/?demo=1) renders an illustrative seeded financial view without authentication. Its internally consistent seeded records demonstrate the review and reporting UI; they are not evidence of bank matching, collection matching, or remittance verification. The [production deployment run 29453848235](https://github.com/upgradedev/archon_nebius/actions/runs/29453848235) completed successfully: the new `archon-backend-r133` Endpoint reached `RUNNING` with `JOB_RUNNER_BACKEND=nebius`, `JOB_QUOTA_PREFLIGHT=1`, and all three exact project-local configurations injected (`project-e00cncsmpr00e8p6knyvdq=eu-north1=vpcsubnet-e00sn2btkrs87k2re4`, `project-e01mmzejpr00e93rgqgf3q=eu-west1=vpcsubnet-e01x810n0mmhj19k9b`, and `project-e03byhh4pr00v15s7dz11p=uk-south1=vpcsubnet-e03w9xd3nbg2abq7qb`). The runtime service account passed Jobs-list permission checks in all three projects, the Object Storage write/read/delete round-trip passed, the Firebase BFF function was updated, and the public `/api/health` probe returned HTTP 200. The [read-only probe](https://github.com/upgradedev/archon_nebius/actions/runs/29452440996) separately establishes three-project Jobs and quota access. Both smoke workflows prove that the API accepted one create request for each configured tuple, but neither proves execution: the short run timed out at nine minutes with all Jobs still `PROVISIONING` at zero instances, while the long run reached `ERROR` around 30 minutes with all three still at zero instances and empty details, then deleted all three. The successful production deployment proves that the live application is configured to orchestrate Nebius Jobs; this article does not claim completion of an application extraction or analysis Job or infer quota exhaustion from the empty error details.

Archon’s direction is straightforward: every successfully extracted document becomes an understandable record; every record has a category and an owner; related records form one financial event; and every validation result identifies the values and source files it compared. That is the foundation for answering the questions a business actually asks — what is this, why was it paid, what is still missing, and does the close reconcile?

---

*Built for the Nebius Serverless AI Builders Challenge 2026. Code: https://github.com/upgradedev/archon_nebius (MIT).*
