# Archon — Agentic Financial Intelligence Platform

> Upload your business documents. Archon extracts, reasons, and delivers a boardroom-ready P&L dashboard — powered by Nebius Serverless AI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Nebius Serverless](https://img.shields.io/badge/Nebius-Serverless%20AI-green)](https://nebius.com)
[![#NebiusServerlessChallenge](https://img.shields.io/badge/%23NebiusServerlessChallenge-2026-orange)](https://nebius.com)

---

## What is Archon?

Archon is a **unified financial intelligence platform** for SMBs. It consolidates a business's financial documents — sales and purchase invoices, orders and receipts, bank statements, payments, payroll, and expenses — into one environment and produces a consolidated, period-over-period view: P&L, EBITDA, per-period metrics, the true cost of the workforce, and cash. It then cross-checks the whole picture to surface what is missing or does not reconcile — for example, a bank payment with no matching invoice, or a bank transfer that understates the true cost of employing a team. It supports **multilingual documents**, handles every common file format, and writes an LLM-authored executive summary.

Built entirely on **Nebius Serverless AI** — a FastAPI orchestration backend running as a **CPU AI Endpoint**, plus two on-demand **CPU AI Jobs** for document extraction and financial analysis. Frontier vision and language models are called over the **Nebius Inference API**, so the containers stay cheap CPU instances and the GPU lives in the inference layer. The React frontend is hosted on Firebase.

---

## Judge Verification

- **Live frontend:** https://archon-pnl.web.app
- **BFF auth path:** `https://archon-pnl.web.app/api/periods` returns `401` when unauthenticated, proving the Firebase proxy/auth gate is live without waiting on the Nebius endpoint.
- **Public repo:** https://github.com/upgradedev/archon_nebius
- **Nebius services used:** AI Endpoint, AI Jobs, Inference API, Object Storage, Managed PostgreSQL, Container Registry
- **Local run:** `docker compose up --build`
- **Core invariant (worked example):** linked payroll events use the full employer cost, not the bank-net transfer — one instance of Archon reconciling a source against its supporting documents, here surfacing the roughly 28% hidden workforce-cost gap.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Firebase Hosting (Google CDN)                  │
│                     React Frontend                              │
│            Ant Design  ·  Recharts  ·  TypeScript               │
│  Upload ──► Job Status ──► P&L Dashboard ──► Executive Report   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST / JSON
┌───────────────────────────▼─────────────────────────────────────┐
│         Nebius Serverless AI Endpoint  (CPU · always-on)        │
│                 FastAPI Orchestration Backend                    │
│   /upload  ·  /jobs  ·  /analyze  ·  /reports                   │
│         JobRunner abstraction (cloud-portable)                  │
└──────┬──────────────────────────────┬────────────────────────────┘
       │ submit job                   │ call endpoint
┌──────▼──────────────────┐  ┌────────▼───────────────────────────┐
│  Nebius Serverless      │  │  Nebius Serverless                 │
│  AI Job (CPU)           │  │  AI Job (CPU)                      │
│  ─────────────────────  │  │  ─────────────────────────────     │
│  Document Extraction    │  │  Financial Analysis Agent          │
│                         │  │                                    │
│  ┌─ Type Detector ─┐    │  │  ┌─ Classifier ──────────────┐    │
│  │ .jpg .png .tiff │─►  │  │  │ invoice/payroll/expense   │    │
│  │ scanned PDF     │ Vision  │  └──────────────────────────┘    │
│  │                 │ LLM  │  │  ┌─ P&L Builder ────────────┐   │
│  │ digital PDF     │─►  │  │  │ monthly aggregation       │   │
│  │ .docx .doc      │ Text│  │  │ ratios · trends           │   │
│  │                 │ LLM  │  │  └──────────────────────────┘   │
│  └─────────────────┘    │  │  ┌─ Executive Narrator ──────┐   │
│           │              │  │  │ LLM-written summary       │   │
│           ▼              │  │  └──────────────────────────┘   │
│     Structured JSON      │  │           │                       │
└──────────┬───────────────┘  └───────────┼───────────────────────┘
           │ write                        │ read / write
┌──────────▼───────────────────────────────▼───────────────────────┐
│                 Nebius Object Storage (S3-compatible)            │
│         raw-docs/  ·  extracted/  ·  reports/                   │
└──────────────────────────────────────────────────────────────────┘
                            │ OpenAI-compatible API
┌───────────────────────────▼──────────────────────────────────────┐
│              Nebius Inference API (studio.nebius.ai)             │
│  Qwen2.5-VL-72B (vision)  ·  Llama-3.3-70B-Instruct (analysis)  │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Upload** — user drops documents (any format) into the React UI
2. **Store** — backend writes raw files to Nebius Object Storage
3. **Extract** — Nebius AI Job spins up, auto-detects each file type, calls vision or text LLM, writes structured JSON per document
4. **Analyze** — a second Nebius AI Job reads all JSONs, runs the 7-stage financial reasoning pipeline, returns chart-ready metrics + executive narrative
5. **Dashboard** — React renders P&L charts, cash flow waterfall, expense breakdown, and the executive summary card

---

## Tech Stack

| Layer | Technology | Hosting |
|---|---|---|
| Frontend | React 18, Vite, TypeScript, Ant Design, Recharts, TanStack Query | Firebase Hosting (Google CDN) |
| Backend | Python 3.12, FastAPI, Pydantic v2, boto3, Caddy (TLS) | **Nebius Serverless AI Endpoint** (CPU `cpu-d3`) |
| Extraction Job | Python 3.12, Qwen2.5-VL-72B (vision), pdfplumber, PyMuPDF, python-docx | **Nebius Serverless AI Job** (CPU `cpu-d3`) |
| Analysis Job | Python 3.12, Llama-3.3-70B-Instruct (7-stage pipeline) | **Nebius Serverless AI Job** (CPU `cpu-d3`) |
| Storage | boto3 (S3-compatible) | Nebius Object Storage |
| Database | PostgreSQL | Nebius Managed PostgreSQL |
| Registry | Docker | Nebius Container Registry |

---

## Quickstart

### Prerequisites

- [Nebius account](https://nebius.com) with credits
- [Nebius CLI](https://docs.nebius.com/cli/install) installed and configured
- [Firebase CLI](https://firebase.google.com/docs/cli) (`npm install -g firebase-tools`)
- Docker 24+
- Node.js 20+
- Python 3.12+

### 1. Clone and configure

```bash
git clone https://github.com/upgradedev/archon_nebius.git
cd archon_nebius
cp .env.example .env
```

Edit `.env` with your Nebius credentials:

```bash
NEBIUS_IAM_TOKEN=your_iam_token_here
NEBIUS_BUCKET_NAME=archon-docs
NEBIUS_PROJECT_ID=your_project_id
NEBIUS_REGION=eu-west1
NEBIUS_INFERENCE_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_INFERENCE_API_KEY=your_inference_api_key
VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct
ANALYSIS_MODEL=meta-llama/Llama-3.3-70B-Instruct
```

### 2. Create object storage bucket

```bash
nebius storage bucket create --name archon-docs
```

### 3. Build, push, and deploy on Nebius

One script builds all three images (backend, extraction job, analysis job), pushes them to the Nebius Container Registry, and deploys the backend as a CPU AI Endpoint:

```bash
bash nebius/redeploy.sh --build
```

The two jobs are submitted on demand by the backend via the Nebius Python SDK — no separate deploy step. (CI/CD alternative: the **Deploy to Nebius** GitHub Actions workflow does the same with repository secrets.)

Then apply the PostgreSQL schema once (the backend persists financial records to
Nebius Managed PostgreSQL; this creates the 6 tables). Not needed for the local
Docker Compose path, which has no database:

```bash
psql "$DATABASE_URL" -f backend/db/schema.sql
```

### 4. Run locally with Docker Compose (no Nebius infrastructure needed)

```bash
cp .env.example .env
# Set ONE value in .env — your Nebius Inference (Studio) API key:
#   NEBIUS_INFERENCE_API_KEY=...
docker compose up --build
```

This brings up the backend, the extraction/analysis containers, a LocalStack S3,
and the frontend. `docker-compose.yml` supplies all the local infra values itself:
it points the stack at LocalStack S3, disables the cloud database, runs jobs as
local containers (`JOB_RUNNER_BACKEND=local`), and bypasses Firebase auth
(`SKIP_AUTH=true`). So you need **no Nebius infrastructure account** — no Jobs,
Endpoints, Object Storage, or PostgreSQL. The only real credential required is the
**Inference API key**, because extraction and analysis call the Nebius Inference
API for the vision and language models (there is no offline mock).

### 5. Try with sample data

The reliable, frontend-independent way to exercise the whole pipeline
(upload → extract → link → validate → analyze → report) is the headless smoke test
— this is exactly what CI runs:

```bash
python scripts/generate-sample-data.py    # synthetic invoices + payroll docs
bash scripts/test-pipeline.sh             # drives the running stack, prints the report JSON
```

You can also use the browser UI at [http://localhost:3000](http://localhost:3000),
but it gates on **Firebase Google sign-in**. To use the UI locally, point
`frontend/src/firebase.ts` at your own Firebase project; otherwise prefer
`test-pipeline.sh` above (or the hosted demo at https://archon-pnl.web.app).

### 6. Deploy the frontend to Firebase

```bash
cd frontend
npm run build
firebase login
firebase use archon-pnl        # replace with your Firebase project ID
firebase deploy
```

The live URL will be printed by the CLI (e.g. `https://archon-pnl.web.app`).
Set this URL as the allowed CORS origin in your backend `.env`:

```bash
CORS_ORIGINS=https://archon-pnl.web.app
```

---

## Testing & CI

Two GitHub Actions pipelines guard every change:

- **Pipeline Smoke Test** (every PR) — gitleaks secret scan → **122 backend unit/integration tests** (pytest) → the **evaluation harness** (below) → frontend tests (Vitest) → a `docker compose` bring-up that runs the pipeline against the local stack.
- **Exhaustive E2E Pipeline** (`e2e/`, on master + weekly) — **44 assertions** drive a live stack through the entire flow (upload → extract → link → validate → analyze → report → dashboard), including the **28% payroll-gap invariant** (`employer_cost_total ≥ bank net`). Run locally with `pytest e2e/` — see [`e2e/README.md`](e2e/README.md).

---

## Evaluation harness (measured accuracy)

> *Evaluation harnesses* is a listed Nebius challenge domain. Archon ships one
> that scores the **real** pipeline agents — not a re-implementation — against a
> labelled synthetic corpus of SMB financial documents, and reports concrete
> field/fusion/validation accuracy. Full detail and findings:
> [`eval/BASELINE.md`](eval/BASELINE.md).

```bash
python eval/generate_corpus.py        # rewrite the committed JSON sample corpus
python eval/evaluate.py               # score the real agents -> table + RESULTS.json
python -m pytest eval/tests -q        # assert the baselines stay true (runs in CI)
```

Offline, **no API key, only `pydantic`**; ~3 s for the 6-case sample, ~6 s for
the deterministic 40-case full corpus (`--n 40 --seed 7`). **Cost: €0** — the
perfect/degraded extractors are deterministic. An optional live slot scores the
real Qwen2.5-VL extractor on Nebius ([`eval/LIVE_EXTRACTION.md`](eval/LIVE_EXTRACTION.md)).

**Measured baselines (full 40-case corpus):**

| Metric | Perfect-extraction ceiling | Degraded (sensitivity) |
|---|---|---|
| Classification accuracy | **100.00%** | 74.29% |
| Field accuracy | **100.00%** | 77.62% |
| Fusion figure accuracy (employer cost via `PnLAgent`) | **100.00%** | 54.05% |
| Validation-outcome accuracy (R1–R4) | **96.88%** | 91.25% |

- **Positive result:** under perfect extraction the `PnLAgent` reports the
  *employer cost* (gross + employer social-security contributions), not the bank
  net, to the cent across 40 diverse cases — the core thesis is verified, and the
  **naive bank-only floor understates workforce cost by EUR 133,381 (~71% over the
  bank figure)** on the corpus.
- **Keystone finding (the harness earns its place):** validation rules **R2 and
  R4 are DORMANT — they fire 0/37 times** because no extractor populates the
  `employer_cost_total` / `net_pay_total` / `employee_count` fields they read
  (the extraction prompt never requests them). R1 and R3 are active and correct.
  See [`eval/BASELINE.md`](eval/BASELINE.md) §3 for the file:line evidence and the
  one-prompt-change fix.

---

## Cloud Portability

Archon is designed to run on any cloud with minimal changes. Only two components are Nebius-specific — both are abstracted behind environment variables.

| Component | Nebius | AWS | Azure | GCP | OCI |
|---|---|---|---|---|---|
| **Frontend** | Firebase Hosting | S3 + CloudFront | Static Web Apps | Firebase Hosting | Object Storage |
| **Backend (Endpoint)** | AI Endpoint (CPU) | ECS / Fargate | Container Apps | Cloud Run | Functions |
| **Batch Jobs** | AI Jobs | AWS Batch | Container Apps Jobs | Cloud Run Jobs | Container Instances |
| **Storage** | Object Storage | S3 | Blob Storage | GCS | Object Storage |
| **Database** | Managed PostgreSQL | RDS | Azure Database | Cloud SQL | Autonomous DB |
| **Registry** | Container Registry | ECR | ACR | Artifact Registry | OCIR |

To switch providers, update the `JOB_RUNNER_BACKEND` and `STORAGE_BACKEND` env vars and replace the two deploy scripts.

---

## Hardware Configuration

| Component | Platform | Preset | Approx. runtime | Approx. cost |
|---|---|---|---|---|
| Backend Endpoint | `cpu-d3` | `4vcpu-16gb` | always-on | ~$0.04 / hr |
| Extraction Job | `cpu-d3` | `4vcpu-16gb` | 3–5 min (20-doc batch), self-terminates | ~$0.01 / run |
| Analysis Job | `cpu-d3` | `4vcpu-16gb` | ~1–2 min, self-terminates | ~$0.01 / run |

> **No always-on GPU.** Every frontier model call runs on the Nebius Inference API, so the containers are cheap CPU instances — the GPU lives in the inference layer. The only always-on cost is the backend endpoint (~$0.04/hr); both jobs are on-demand and self-terminate. PostgreSQL and Object Storage are negligible and should be left running to preserve data.

---

## Sample Output

A `POST /analyze` call returns a structured `FinancialReport` JSON. Abbreviated example:

```json
{
  "period": "2026-01",
  "generated_at": "2026-01-31T14:22:01Z",
  "pnl": {
    "total_revenue": 48500.00,
    "total_expenses": 31200.00,
    "net_profit": 17300.00,
    "gross_margin_pct": 35.7,
    "operating_margin_pct": 28.4,
    "payroll_cost_total": 18400.00,
    "payroll_cost_bank_net": 14350.00,
    "payroll_gap_pct": 28.2
  },
  "cash_flow": {
    "operating": 15200.00,
    "investing": -3400.00,
    "financing": 0.00,
    "net": 11800.00
  },
  "employees": [
    { "name": "J. Andersen", "gross_salary": 2400.00, "employer_cost": 2976.00 }
  ],
  "executive_summary": "January 2026 shows a healthy 28.4% operating margin. Payroll represents the largest cost centre at €18,400 — 28% above what the bank transfer alone would suggest, reflecting employer social-security contributions. Cash position improved by €11,800...",
  "validation": { "rules_passed": 4, "rules_failed": 0 }
}
```

The React dashboard renders this as:
- Monthly P&L trend chart (revenue / expenses / net profit)
- Cash flow waterfall (operating / investing / financing)
- Expense breakdown by category (donut chart)
- Per-employee salary analytics table
- Key ratios: gross margin, operating margin, burn rate
- LLM-written executive summary card

---

## Managing Costs

The only always-on component is the backend CPU endpoint (~$0.04/hr); both AI Jobs are on-demand and self-terminate, so there is no GPU running between sessions. To stop the backend endpoint entirely between demos:

**GitHub Actions (recommended — no local CLI needed):**
> Actions → **Teardown Nebius Resources** → Run workflow → choose scope

**Local script:**
```bash
bash nebius/teardown.sh            # delete the backend endpoint

bash nebius/redeploy.sh            # redeploy with existing images
bash nebius/redeploy.sh --build    # rebuild images + redeploy
```

Always kept running (negligible cost): Nebius Managed PostgreSQL · Object Storage · Firebase Hosting

---

## Proof of Execution

This project runs on Nebius Serverless AI infrastructure:

- **Backend AI Endpoint** (CPU `cpu-d3`) — target backend behind the Firebase BFF. Unauthenticated `GET https://archon-pnl.web.app/api/periods` returns `401` at the proxy/auth gate; authenticated upload/analyze requests require the Nebius endpoint deployment to be restored. List the endpoint with `nebius ai endpoint list --parent-id <project-id>`.
- **Extraction & Analysis AI Jobs** (CPU `cpu-d3`) — submitted on demand by the backend via the Nebius Python SDK; completed runs appear in `nebius ai job list`.
- **Object Storage** — bucket `archon-bucket` with `raw-docs/`, `extracted/`, and `reports/` prefixes.
- **Managed PostgreSQL** — cluster `postgresql-e01mek1w9re2vdxc8g`, 6 tables live (`documents`, `employees`, `payroll_events`, `employee_payroll`, `validation_results`, `financial_reports`).

---

## License

MIT — see [LICENSE](LICENSE)

---

*Submitted to the [Nebius Serverless AI Builders Challenge 2026](https://nebius.com) — #NebiusServerlessChallenge*
