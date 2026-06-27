# Sample Data

This directory contains **synthetic** Greek business documents for testing and demonstration.

All data is fictional. No real company names, tax IDs, or financial figures are used.

## Contents

```
sample-data/
├── invoices/        Greek vendor invoices (PDF + scanned JPG)
├── payroll/         Monthly payroll reports (PDF)
└── expenses/        Expense receipts (JPG photos)
```

## Generating synthetic documents

```bash
python scripts/generate-sample-data.py
```

This creates 15 realistic synthetic Greek documents in the directories above.

## Using with Archon

1. Start Archon locally: `docker compose up`
2. Open http://localhost:3000
3. Select a reporting period (e.g. 2026-04)
4. Drag all files from this directory into the upload area
5. Click **Extract & Analyze**

Expected runtime on Nebius CPU Jobs plus the Nebius Inference API: **3–5 minutes** for a typical 15-document batch.
Expected Nebius job cost: **~$0.02–$0.05** per run, depending on Inference API token usage.
