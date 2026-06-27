# Archon — Agentic Financial Intelligence Platform

> Upload your business documents. Archon extracts, reasons, and delivers a boardroom-ready P&L dashboard — powered by Nebius Serverless AI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Nebius Serverless](https://img.shields.io/badge/Nebius-Serverless%20AI-green)](https://nebius.com)
[![#NebiusServerlessChallenge](https://img.shields.io/badge/%23NebiusServerlessChallenge-2026-orange)](https://nebius.com)

---

## What is Archon?

Archon is an end-to-end agentic pipeline that turns raw business documents — scanned invoices, payroll PDFs, vendor bills, expense photos — into structured financial intelligence. It supports **multilingual documents** (including Greek), handles every common file format, and produces a modern dashboard with P&L trends, cash flow analysis, and an LLM-written executive summary.

Built entirely on **Nebius Serverless AI** — a FastAPI orchestration backend running as a **CPU AI Endpoint**, plus two on-demand **CPU AI Jobs** for document extraction and financial analysis. Frontier vision and language models are called over the **Nebius Inference API**, so the containers stay cheap CPU instances and the GPU lives in the inference layer. The React frontend is hosted on Firebase.

---

## Judge Verification

- **Live frontend:** https://archon-pnl.web.app
- **BFF auth path:** `https://archon-pnl.web.app/api/periods` returns `401` when unauthenticated, proving the Firebase proxy/auth gate is live without waiting on the Nebius endpoint.
- **Public repo:** https://github.com/upgradedev/archon_nebius
- **Nebius services used:** AI Endpoint, AI Jobs, Inference API, Object Storage, Managed PostgreSQL, Container Registry
- **Local run:** `docker compose up --build`
- **Core invariant:** linked payroll events use employer payroll cost, not bank-net transfer, surfacing the roughly 28% hidden payroll gap.

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
git clone https://github.com/YOUR_USERNAME/archon.git
cd archon
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

### 4. Run locally with Docker Compose

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000)

### 5. Try with sample data

```bash
python scripts/generate-sample-data.py   # generates synthetic Greek invoices
# Then upload the files from sample-data/ via the UI
```

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

- **Pipeline Smoke Test** (every PR) — gitleaks secret scan → **122 backend unit/integration tests** (pytest) → frontend tests (Vitest) → a `docker compose` bring-up that runs the pipeline against the local stack.
- **Exhaustive E2E Pipeline** (`e2e/`, on master + weekly) — **44 assertions** drive a live stack through the entire flow (upload → extract → link → validate → analyze → report → dashboard), including the **28% payroll-gap invariant** (`employer_cost_total ≥ bank net`). Run locally with `pytest e2e/` — see [`e2e/README.md`](e2e/README.md).

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
    { "name": "Παπαδόπουλος Γ.", "gross_salary": 2400.00, "employer_cost": 2976.00 }
  ],
  "executive_summary": "January 2026 shows a healthy 28.4% operating margin. Payroll represents the largest cost centre at €18,400 — 28% above what the bank transfer alone would suggest, reflecting IKA employer contributions. Cash position improved by €11,800...",
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
