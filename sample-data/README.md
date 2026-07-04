# Sample Data

This directory holds **synthetic**, locale-neutral business documents for testing
and demonstration. All data is fictional — no real company names, tax IDs, or
financial figures.

## Generating the documents

```bash
pip install reportlab
python scripts/generate-sample-data.py
```

This writes **7 synthetic PDFs** to `sample-data/generated/` (gitignored — the
script is committed, the output is not), one per Archon document category:

```
sample-data/generated/
├── toll_invoice_202601.pdf           services invoice (EUR, domestic VAT)
├── anthropic_invoice_202601.pdf       SaaS invoice (USD, reverse charge)
├── aws_invoice_202601.pdf             cloud invoice (USD, reverse charge)
├── payroll_register_202601.pdf        payroll register (gross · net · employer cost)
├── bank_confirmation_202601.pdf       batch payroll transfer confirmation
├── payslip_emp001_202601.pdf          individual payslip
└── google_statement_202601.pdf        vendor account statement
```

Together they cover every Archon document type: `invoice`, `account_statement`,
`payroll_register`, `bank_confirmation`, and `payslip`. (Archon extracts
multilingual documents; these samples are kept locale-neutral English.)

## Running the pipeline on them

The reliable, frontend-independent way to exercise the whole pipeline
(upload → extract → link → validate → analyze → report) is the headless smoke
test — the same path CI runs:

```bash
python scripts/generate-sample-data.py    # writes the 7 PDFs above
bash scripts/test-pipeline.sh             # drives the running stack, prints the report JSON
```

`test-pipeline.sh` needs the local stack up (`docker compose up --build`) and one
credential — your Nebius Inference API key in `.env` (see the top-level
[README](../README.md) Quickstart).

The browser UI at `http://localhost:3000` also works, but it gates on Firebase
Google sign-in, so it needs **your own Firebase project** wired into
`frontend/src/firebase.ts`. For a self-contained run prefer `test-pipeline.sh`
above (or the hosted demo at https://archon-pnl.web.app).

Expected runtime on Nebius CPU Jobs plus the Nebius Inference API: **1–3 minutes**
for this batch. Expected Nebius job cost: **~$0.02** per run, depending on
Inference API token usage.
