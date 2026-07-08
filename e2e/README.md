# Exhaustive End-to-End Pipeline Tests

Drives a **live Archon stack** through the entire pipeline and asserts on every
stage:

```
/api/upload → /api/jobs (extraction) → documents.json
            → /api/analyze → report.json → /api/periods · /api/documents · /api/reports
```

Unlike `scripts/test-pipeline.sh` (a thin smoke test that prints JSON), this
suite makes **assertions** — including Archon's core invariant: a detected
payroll event's `employer_cost_total` must exceed the bank-net transfer (the
~72% gap the EventLinker fuses).

## Layout

| File | Stage |
|---|---|
| `test_01_health.py` | stack up; OpenAPI contract present |
| `test_02_upload_validation.py` | input guardrails (period, file type, count, traversal) — deterministic, no LLM |
| `test_03_pipeline.py` | full pipeline (shared session run) + deep report assertions + the payroll-gap invariant |
| `test_04_periods_reports.py` | dashboard endpoints + period delete/lifecycle (runs last) |

The expensive upload→extract→analyze run happens **once** per session
(`completed_pipeline` fixture in `conftest.py`) and is shared across assertions.

## Run locally

Start the stack, then point the suite at it:

```bash
# 1. bring up the local stack
cp .env.example .env            # set NEBIUS_INFERENCE_API_KEY; JOB_RUNNER_BACKEND=local; SKIP_AUTH=true
python scripts/generate-sample-data.py
docker compose up --build -d localstack extraction analysis backend
aws --endpoint-url=http://localhost:4566 s3 mb s3://archon-bucket   # one-time

# 2. run the exhaustive E2E
pip install -r e2e/requirements.txt
BACKEND_URL=http://localhost:8000 python -m pytest e2e/ -v
```

## Configuration (env)

| Var | Default | Purpose |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | backend base URL |
| `STORAGE_ENDPOINT_URL` | `http://localhost:4566` | localstack S3 (storage-layer assertions; degrade to skip if unreachable) |
| `NEBIUS_BUCKET_NAME` | `archon-bucket` | bucket |
| `E2E_PERIOD` | `2026-01` | period under test (deleted at the end) |
| `E2E_EXTRACT_TIMEOUT_S` | `420` | max wait for extraction to complete |

## CI

Runs in `.github/workflows/e2e.yml` — on **push to master**, **manual dispatch**,
and **weekly** (Mondays 04:00 UTC). It makes real, billable model calls, so it is
deliberately **not** on every PR; the per-PR gate is the fast `Pipeline Smoke
Test` (`smoke-test.yml`).
