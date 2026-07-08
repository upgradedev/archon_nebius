# Building Archon: an Agentic Financial Intelligence Platform on Nebius Serverless AI

*#NebiusServerlessChallenge · #ServerlessAI · #FinTech · #LLM*

---

Small-business finance has a quiet failure mode: the numbers look clean while the underlying documents disagree. A company's financial truth is scattered across dozens of document types — sales and purchase invoices, orders, receipts, payments, bank transfers and statements, payroll, expenses — and each one is entered, mis-entered, or never entered by a different hand.

**Archon** is a unified financial intelligence platform that ingests all of it into one environment and produces a consolidated, period-over-period view — P&L, EBITDA, per-period metrics, total workforce cost, cash — then cross-checks the whole picture to surface what is missing or does not reconcile. It reads scanned and digital documents in multiple languages and writes an LLM-authored executive summary on top.

This post is about the engineering: the document-fusion insight the product is built around, the multi-agent architecture on **Nebius Serverless AI**, and the trust design that lets a language model near a financial report without ever touching the arithmetic.

> **Architecture diagram:** the full component graph (frontend → BFF → CPU endpoint → jobs → storage/DB/inference) is rendered in the [repository README](https://github.com/upgradedev/archon_nebius#architecture).

## The insight: one event, three documents, three different truths

The clearest example of "the documents disagree" is a single payroll event, which produces three artifacts that each tell a different part of the truth:

| Document | What it reports | Amount (one employee) |
|---|---|---|
| Bank confirmation | Net salary transferred to the employee | €1,430 |
| Payslip | Gross − employee contributions − tax | €1,430 net / €2,000 gross |
| Payroll register | Gross **+ employer** contributions | €2,446 true cost |

The business actually spends about **€2,446** to employ that person, but the bank debit only shows **€1,430**. Software that reads only the bank statement silently under-reports workforce cost — here the true employer cost is about **72% above** what left the bank (the employer's own social-security contribution alone is ~35% of the transfer; the rest is the tax and social security withheld from the employee), and payroll is the single largest cost centre for most SMBs.

No single document can be trusted alone. The fix is to *fuse* the three into one event and read the right figure for the right question. That is a dedicated agent:

```python
# jobs/extraction/agents/event_linker.py
def _build_event(company, period, docs):
    bank      = _pick_one(docs, DocType.BANK_CONFIRMATION)
    register  = _pick_one(docs, DocType.PAYROLL_REGISTER)
    payslips  = [d for d in docs if d.doc_type == DocType.PAYSLIP]

    is_complete = all([bank is not None, register is not None, len(payslips) > 0])
    return PayrollEvent(period=period, company_name=company or None,
                        bank_confirmation=bank, payroll_register=register,
                        payslips=payslips, is_complete=is_complete)
```

Once linked, the P&L uses the register's employer cost while cash-flow analysis uses the bank transfer — the same event counted once, correctly, from two angles. The same reconciliation shape extends to vendors: a `ReconciliationAgent` flags invoices a vendor statement references but the system never received.

## Why Nebius Serverless AI fit the workload

The workload is bursty. A customer uploads documents once a month, waits for processing, then may not run another batch for weeks — a poor fit for an always-on GPU. Archon uses three Nebius compute primitives instead:

- a **CPU AI Endpoint** for the always-on FastAPI orchestration backend (`/upload · /jobs · /analyze · /reports`);
- a **CPU AI Job for extraction** that starts on upload, processes the batch, writes JSON, and self-terminates;
- a **CPU AI Job for analysis** that reads the extracted JSON, builds the report, and self-terminates.

The decisive choice is that **the GPU is not inside Archon's containers**. Extraction and analysis are cheap CPU Python containers that call the **Nebius Inference API** over HTTP — Qwen2.5-VL-72B for vision extraction, Llama-3.3-70B for narration. The frontier models live in Nebius's inference layer; Archon's containers stay disposable. The only always-on cost is a ~$0.04/hr CPU endpoint; each job run costs about a cent. Object Storage holds the raw, extracted, and report artifacts; Managed PostgreSQL holds the durable financial records; Container Registry hosts the three images. Six Nebius services, one workflow.

The React frontend and a thin BFF route sit on Firebase — public hosting, login, and browser-edge TLS. The honest claim is precise: **all domain compute and stateful financial infrastructure run on Nebius; Firebase is only the public edge.**

## Two agent pipelines

**Extraction (4 agents)** turns raw files into structured JSON. `ExtractorAgent` auto-detects file type and routes digital text to text extraction, scans and images to the vision model. `ClassifierAgent` then *deterministically* refines the document type — keeping common LLM misclassifications out of the accounting layer. `EventLinkerAgent` fuses the payroll triad (above). `ValidatorAgent` runs cross-document consistency checks.

**Analysis (7 agents)** turns that JSON into a dashboard-ready report: re-classify, then `PnLAgent`, `CashFlowAgent`, `EmployeeAgent`, `ReconciliationAgent`, a `ValidatorAgent` safety net, and finally `NarratorAgent` for the executive summary. Each agent is single-responsibility — easy to test and easy to reason about.

## Trust: the numbers are deterministic, the LLM only narrates

For a financial product, "a language model computed your P&L" is a non-starter. Archon is built so it never does. Every figure — P&L, expense breakdown, vendor summaries, key metrics — is pure Python arithmetic:

```python
# jobs/analysis/agents/pnl_agent.py
"""
PnLAgent — aggregates extracted documents into P&L metrics.
Single responsibility: pure Python arithmetic over classified documents.
No LLM call; deterministic and fast.
"""
def build_pnl(period, docs):
    revenue  = sum(d.total_amount for d in docs if d.doc_type in REVENUE_DOC_TYPES)
    expenses = _compute_expenses(docs)
    net_profit = revenue - expenses
    return MonthlyPnL(period=period, revenue=round(revenue, 2),
                      expenses=round(expenses, 2), netProfit=round(net_profit, 2), ...)
```

The only place a model touches the analysis is `NarratorAgent`, which writes a three-to-four-sentence summary *from the already-computed metrics*. If that call fails, the report still renders — the narrative is the garnish, not the meal. The numbers you see are not hallucinated; they are `round(sum(...), 2)`.

The cross-document checks are equally auditable. `ValidatorAgent` runs four named, deterministic rules with explicit tolerances — e.g. `R1: bank.total ≈ Σ payslips ±2%`, `R2: employer_cost / net_pay ∈ [1.25, 1.45]`, `R3: bank date ≤ period end`, `R4: register headcount == payslip count`. Every flag cites the rule, the two figures compared, and the source files — a finding you can check by hand, not "the model thought something looked off."

## Measuring it — and an honest caveat

A claim like "we surface the ~72% gap" is worth nothing without a number behind it, so the repo ships an **evaluation harness** (`eval/`) that scores the *real* pipeline agents against a labelled synthetic corpus. It runs offline, no API key, only `pydantic`:

```bash
python eval/generate_corpus.py && python eval/evaluate.py
```

On the deterministic 40-case corpus, under perfect extraction the `PnLAgent` reports employer cost to the cent, and the naive bank-only view understates workforce cost by **€133,381 (~72% over the bank figure)** across the corpus. The thesis is verified, not asserted.

The uncomfortable result — the entire reason to build a harness — is that two of the four validation rules are **dormant**: R2 and R4 fire 0/37 times because they read fields (`employer_cost_total`, `net_pay_total`, `employee_count`) the extraction prompt never requests. The harness turns that from an unknown into a measured 0/37 with file-and-line evidence and a one-prompt fix, written up in [`eval/BASELINE.md`](https://github.com/upgradedev/archon_nebius/blob/master/eval/BASELINE.md). Finding it before a customer does is the whole point.

## One lesson worth keeping: a serverless job can lie to you

A Nebius AI Job is a *request* for compute, not a guarantee. Quota is granted per compute preset, and when a preset has zero quota the platform does something worse than reject you: it *accepts* the job, strands it in `PROVISIONING`, never allocates an instance, and tears it down with no error. Your submission returned a job id. Nothing is coming.

Archon now treats this as a first-class failure mode. It submits, probes for a real instance within a bounded window, and on a *never-provisioned* outcome deletes the stalled job and climbs a config-driven preset ladder — failing over only when a job never got compute, never when a job reached compute and then crashed (that bug would recur on every rung). If every rung fails, the API returns one actionable `503`, not a silent spinner. The full taxonomy is in [`docs/capacity-probe-pattern.md`](https://github.com/upgradedev/archon_nebius/blob/master/docs/capacity-probe-pattern.md), reproducible offline with `bash scripts/demo-failover.sh`.

One more detail bit us: when the backend submits a job, Nebius must pull the image, and registry credentials belong on the job spec itself as a **single** message, not a list:

```python
# backend/services/nebius.py
registry_credentials=JobSpec.RegistryCredentials(username="iam", password=token)
```

Treating it as repeated turns job submission into a 500. Small detail; real outage.

## Try it

The local stack needs no Nebius account — just an Inference API key. LocalStack stands in for object storage; jobs run as local containers:

```bash
git clone https://github.com/upgradedev/archon_nebius && cd archon_nebius
cp .env.example .env          # set NEBIUS_INFERENCE_API_KEY
docker compose up --build
bash scripts/test-pipeline.sh # drives the full pipeline, prints the report JSON
```

Or see the payoff with zero setup: **https://archon-pnl.web.app/?demo=1** renders a full sample report — P&L, charts, validations, executive summary — entirely client-side, no backend call.

That is the point of the build: once Nebius handles the serverless compute and inference surfaces, the hard work moves back where it belongs — domain correctness.

---

*Built for the Nebius Serverless AI Builders Challenge 2026. Code: https://github.com/upgradedev/archon_nebius (MIT).*
