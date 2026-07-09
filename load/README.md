# Load testing (k6)

The **load tier** of Archon's testing pyramid. The gating pipelines (unit ·
integration · E2E — see the repo [`README` → Testing & CI](../README.md#testing--ci))
prove *correctness*; this proves the HTTP/service layer holds its latency and
error-rate SLOs under a ramp of concurrent virtual users.

It is an **opt-in / manual** target — deliberately **not** a PR gate. A load test
needs a running backend and reports capacity, not pass/fail correctness, so it
lives outside the merge gate (mirrors the sibling `qwen-memoryagent/load/`).

## What it targets

[`health-load.js`](health-load.js) drives `GET ${BASE_URL}/api/health` — the
unauthenticated liveness probe the frontend polls through the Firebase BFF to
detect cold-start recovery. It is a pure in-process handler (no auth, no DB, no
model call), so it isolates the raw serving capacity of the CPU endpoint: how the
FastAPI/uvicorn layer behaves as concurrency climbs, independent of the expensive
upload/analyze paths and **without incurring any Inference-API spend**. Read-only
and auth-free by design, so it is safe to point at the live endpoint.

Profile: a 20s single-VU **smoke** followed by a **ramp** 0 → 20 → 0 VUs over
~90s. SLOs (thresholds — the run fails if any is crossed):

| Metric | Threshold |
|---|---|
| `http_req_duration{endpoint:health}` p95 | < 500 ms |
| `http_req_duration{endpoint:health}` p99 | < 800 ms |
| `http_req_failed` | < 1% |
| `checks` pass rate | > 99% |

## Install k6

k6 is a single static binary — see the
[official install guide](https://grafana.com/docs/k6/latest/set-up/install-k6/).

```bash
# macOS
brew install k6
# Debian/Ubuntu
sudo gpg -k && sudo apt-get install k6      # after adding the k6 apt repo
# Windows
winget install k6 --source winget           # or: choco install k6
# Any OS: download the release binary from https://github.com/grafana/k6/releases
```

## Run

```bash
# Against a locally-running backend (default BASE_URL=http://localhost:8000):
#   cd backend && SKIP_AUTH=true JOB_RUNNER_BACKEND=local python -m uvicorn main:app --port 8000
# or the full stack: docker compose up --build backend
k6 run load/health-load.js

# Against the live endpoint (through the Firebase BFF — /api/health is public):
k6 run -e BASE_URL=https://archon-pnl.web.app load/health-load.js

# Smoke only (skip the ramp — a ~20s sanity pass):
RUN_RAMP=false k6 run load/health-load.js
```

### Env knobs

| Var | Default | Purpose |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Backend origin; `/api/health` is appended. Pass the BFF origin (`https://archon-pnl.web.app`) or the backend origin directly. |
| `RUN_RAMP` | `true` | `false` → smoke only (no ramp). |

Each run writes a machine-readable `load-summary.json` alongside the stdout
summary (uploaded as a CI artifact by
[`.github/workflows/load-test.yml`](../.github/workflows/load-test.yml)).

## CI

`load-test.yml` runs the same smoke on demand only (**`workflow_dispatch`**):
GitHub Actions → **Load Test (k6)** → *Run workflow*, or
`gh workflow run load-test.yml`. It boots the backend with `python -m uvicorn`
(no Docker, no Nebius credentials — `JOB_RUNNER_BACKEND=local` short-circuits the
startup permission check) and runs `health-load.js` against it. Being manual-only,
it never blocks a PR.
