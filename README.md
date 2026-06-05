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
│      Qwen2-VL-72B (vision)  ·  Qwen2.5-72B (analysis)           │
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
| AI Job | Python 3.12, Qwen2-VL (vision), pdfplumber, PyMuPDF, python-docx | Nebius Serverless AI Job |
| AI Endpoint | Python 3.12, FastAPI, Qwen2.5-72B (analysis agent) | Nebius Serverless AI Endpoint |
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

| Component | Platform | Preset | Approx. cost |
|---|---|---|---|
| Extraction Job | `gpu-l40s-a` | `1gpu-8vcpu-32gb` | ~$0.15 / run |
| Analysis Endpoint | `gpu-l40s-a` | `1gpu-8vcpu-32gb` | ~$0.90 / hr |

Approximate runtime for a 20-document batch: **3–5 minutes**.

---

## Sample Output

- Monthly P&L trend chart (revenue / expenses / net profit)
- Cash flow waterfall (operating / investing / financing)
- Expense breakdown by category (donut chart)
- Top vendors table with invoice aging
- Key ratios: gross margin, operating margin, burn rate
- LLM-written executive summary in English

---

## License

MIT — see [LICENSE](LICENSE)

---

*Submitted to the [Nebius Serverless AI Builders Challenge 2026](https://nebius.com) — #NebiusServerlessChallenge*
