# Archon — Agentic Financial Intelligence Platform

> Upload your business documents. Archon extracts, reasons, and delivers a boardroom-ready P&L dashboard — powered by Nebius Serverless AI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Nebius Serverless](https://img.shields.io/badge/Nebius-Serverless%20AI-green)](https://nebius.com)
[![#NebiusServerlessChallenge](https://img.shields.io/badge/%23NebiusServerlessChallenge-2026-orange)](https://nebius.com)

---

## What is Archon?

Archon is an end-to-end agentic pipeline that turns raw business documents — scanned invoices, payroll PDFs, vendor bills, expense photos — into structured financial intelligence. It supports **multilingual documents** (including Greek), handles every common file format, and produces a modern dashboard with P&L trends, cash flow analysis, and an LLM-written executive summary.

Built on **Nebius Serverless AI Jobs** (batch extraction) and **Nebius Serverless AI Endpoints** (financial analysis agent), with a React frontend hosted on Firebase and a FastAPI orchestration layer running on Nebius Compute.

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
│              Nebius Compute VM  (CPU · always-on)               │
│                 FastAPI Orchestration Backend                    │
│   /upload  ·  /jobs  ·  /analyze  ·  /reports                   │
│         JobRunner abstraction (cloud-portable)                  │
└──────┬──────────────────────────────┬────────────────────────────┘
       │ submit job                   │ call endpoint
┌──────▼──────────────────┐  ┌────────▼───────────────────────────┐
│  Nebius Serverless      │  │  Nebius Serverless                 │
│  AI Job                 │  │  AI Endpoint                       │
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
│   Qwen2-VL-72B (vision)  ·  Llama-3.3-70B-Instruct (analysis)   │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Upload** — user drops documents (any format) into the React UI
2. **Store** — backend writes raw files to Nebius Object Storage
3. **Extract** — Nebius AI Job spins up, auto-detects each file type, calls vision or text LLM, writes structured JSON per document
4. **Analyze** — Nebius AI Endpoint reads all JSONs, runs agentic financial reasoning, returns chart-ready metrics + executive narrative
5. **Dashboard** — React renders P&L charts, cash flow waterfall, expense breakdown, and the executive summary card

---

## Tech Stack

| Layer | Technology | Hosting |
|---|---|---|
| Frontend | React 18, Vite, TypeScript, Ant Design, Recharts, TanStack Query | Firebase Hosting (Google CDN) |
| Backend | Python 3.12, FastAPI, Pydantic v2, boto3 | Nebius Compute VM (CPU) |
| AI Job | Python 3.12, Qwen2-VL-72B (vision), pdfplumber, PyMuPDF, python-docx | Nebius Serverless AI Job |
| AI Endpoint | Python 3.12, FastAPI, Llama-3.3-70B-Instruct (analysis agent) | Nebius Serverless AI Endpoint |
| Storage | boto3 (S3-compatible) | Nebius Object Storage |
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
NEBIUS_REGION=eu-north1
NEBIUS_INFERENCE_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_INFERENCE_API_KEY=your_inference_api_key
```

### 2. Create object storage bucket

```bash
nebius storage bucket create --name archon-docs
```

### 3. Deploy the extraction job image

```bash
cd jobs/extraction
docker build -t cr.nebius.com/YOUR_PROJECT/archon-extraction:latest .
docker push cr.nebius.com/YOUR_PROJECT/archon-extraction:latest
cd ../..
```

### 4. Deploy the analysis endpoint

```bash
cd endpoints/analysis
docker build -t cr.nebius.com/YOUR_PROJECT/archon-analysis:latest .
docker push cr.nebius.com/YOUR_PROJECT/archon-analysis:latest
cd ../..

# Deploy as Nebius Serverless AI Endpoint
bash nebius/deploy-endpoint.sh
```

### 5. Run locally with Docker Compose

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000)

### 6. Try with sample data

```bash
python scripts/generate-sample-data.py   # generates synthetic Greek invoices
# Then upload the files from sample-data/ via the UI
```

### 7. Deploy the frontend to Firebase

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

## Cloud Portability

Archon is designed to run on any cloud with minimal changes. Only two components are Nebius-specific — both are abstracted behind environment variables.

| Component | Nebius | AWS | Azure | GCP | OCI |
|---|---|---|---|---|---|
| **Frontend** | Firebase Hosting | S3 + CloudFront | Static Web Apps | Firebase Hosting | Object Storage |
| **Backend** | Compute VM | EC2 / ECS | Container Apps | Cloud Run | Compute |
| **Batch Job** | AI Jobs | AWS Batch | Container Apps Jobs | Cloud Run Jobs | Container Instances |
| **Endpoint** | AI Endpoints | ECS / Fargate | Container Apps | Cloud Run | Functions |
| **Storage** | Object Storage | S3 | Blob Storage | GCS | Object Storage |
| **Registry** | Container Registry | ECR | ACR | Artifact Registry | OCIR |

To switch providers, update the `JOB_RUNNER_BACKEND` and `STORAGE_BACKEND` env vars and replace the two deploy scripts.

---

## Hardware Configuration

| Component | Platform | Preset | Approx. runtime | Approx. cost |
|---|---|---|---|---|
| Extraction Job | `gpu-l40s-a` | `1gpu-8vcpu-32gb` | 3–5 min (20-doc batch) | ~$0.15 / run |
| Analysis Endpoint | `gpu-l40s-a` | `1gpu-8vcpu-32gb` | ~90s cold start | ~$0.90 / hr |
| Backend VM | CPU (4 vCPU / 8 GB) | — | always-on | ~$0.03 / hr |

> **Cost tip:** Tear down the analysis endpoint between sessions — it accounts for ~95% of running costs. PostgreSQL and Object Storage are negligible and should be left running to preserve data.

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

The analysis endpoint (~$0.90/hr) should be stopped after each session. Two options:

**GitHub Actions (recommended — no local CLI needed):**
> Actions → **Teardown Nebius Resources** → Run workflow → choose scope

**Local script:**
```bash
bash nebius/teardown.sh            # endpoint only
bash nebius/teardown.sh --all      # endpoint + backend VM

bash nebius/redeploy.sh            # redeploy with existing images
bash nebius/redeploy.sh --build    # rebuild images + redeploy
```

Always kept running (negligible cost): Nebius Managed PostgreSQL · Object Storage · Firebase Hosting

---

## Proof of Execution

This project ran on Nebius Serverless AI infrastructure:

- **Extraction Job** — `nebius ai job list` output showing completed jobs processing `raw-docs/2026-01/`
- **Analysis Endpoint** — `aiendpoint-e01xgdhk0skzdcnfpf` deployed on `gpu-l40s-a`, responding at `http://66.201.5.233:8001`
- **Object Storage** — seeded bucket `archon-bucket` with `raw-docs/`, `extracted/`, and `reports/` prefixes
- **PostgreSQL** — cluster `postgresql-e01mek1w9re2vdxc8g`, 6 tables live (`documents`, `employees`, `payroll_events`, `employee_payroll`, `validation_results`, `financial_reports`)

---

## License

MIT — see [LICENSE](LICENSE)

---

*Submitted to the [Nebius Serverless AI Builders Challenge 2026](https://nebius.com) — #NebiusServerlessChallenge*
