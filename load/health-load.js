// k6 load / performance test for the Archon (Nebius) FastAPI backend.
//
// This is the LOAD tier of the testing pyramid. The gating pipelines (unit ·
// integration · E2E — see README "Testing & CI") prove *correctness*; this
// proves the HTTP/service layer holds its latency + error-rate SLOs under a
// ramp of concurrent virtual users. It is an OPT-IN / MANUAL target, NOT a PR
// gate (see .github/workflows/load-test.yml, workflow_dispatch only).
//
// ── What it targets ─────────────────────────────────────────────────────────
// GET ${BASE_URL}/api/health — the unauthenticated liveness probe the frontend
// polls through the Firebase BFF to detect cold-start recovery. It is a pure,
// in-process handler (no auth, no DB, no model call), so it isolates the raw
// serving capacity of the CPU endpoint: how the FastAPI/uvicorn layer behaves
// as concurrency climbs, independent of the expensive upload/analyze paths and
// without incurring any Inference-API spend. Keeping the load read-only and
// auth-free is deliberate — it is safe to run against the live endpoint.
//
// ── Run ─────────────────────────────────────────────────────────────────────
//   k6 run load/health-load.js                                   # localhost:8000
//   k6 run -e BASE_URL=https://archon-pnl.web.app load/health-load.js   # live (via BFF)
//   RUN_RAMP=false k6 run load/health-load.js                    # skip the ramp (smoke only)
//
// ── Env knobs ───────────────────────────────────────────────────────────────
//   BASE_URL   base URL of the backend (default http://localhost:8000). The
//              /api/health path is appended, so pass the origin the BFF serves
//              (e.g. https://archon-pnl.web.app) or the backend origin directly.
//   RUN_RAMP   'false' → smoke only; anything else (default) → run the ramp too.

import http from "k6/http";
import { check, sleep } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

const BASE = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const RUN_RAMP = (__ENV.RUN_RAMP || "true").toLowerCase() !== "false";

// ── Scenarios ────────────────────────────────────────────────────────────────
// smoke: 1 VU for ~20s — a fast, cheap sanity pass that always runs.
// ramp:  0→20→0 over ~90s — the actual load profile; starts AFTER the smoke so
//        the two never overlap and the summary stays interpretable.
const scenarios = {
  smoke: {
    executor: "constant-vus",
    vus: 1,
    duration: "20s",
    tags: { scenario: "smoke" },
  },
};
if (RUN_RAMP) {
  scenarios.ramp = {
    executor: "ramping-vus",
    startVUs: 0,
    startTime: "22s", // begin just after the 20s smoke finishes
    stages: [
      { duration: "30s", target: 20 }, // ramp up to 20 concurrent VUs
      { duration: "30s", target: 20 }, // hold at 20
      { duration: "30s", target: 0 },  // ramp back down
    ],
    gracefulRampDown: "5s",
    tags: { scenario: "ramp" },
  };
}

// ── Thresholds (SLOs) ──────────────────────────────────────────────────────
// /api/health is a trivial in-process handler, so it should be fast even under
// load. A blown threshold here is a real serving-capacity regression.
export const options = {
  scenarios,
  thresholds: {
    http_req_failed: ["rate<0.01"], // <1% of requests may fail
    checks: ["rate>0.99"], // >99% of assertions must pass
    "http_req_duration{endpoint:health}": ["p(95)<500", "p(99)<800"],
    // Loose global ceiling; the tagged SLO above is the meaningful one.
    http_req_duration: ["p(95)<500"],
  },
};

// ── Test body ────────────────────────────────────────────────────────────────
export default function () {
  const res = http.get(`${BASE}/api/health`, { tags: { endpoint: "health" } });
  const body = safeJson(res) || {};
  check(
    res,
    {
      "health: 200": (r) => r.status === 200,
      "health: status ok": () => body.status === "ok",
      "health: reports service": () => typeof body.service === "string",
    },
    { endpoint: "health" }
  );
  sleep(1);
}

function safeJson(res) {
  try {
    return res.json();
  } catch (_e) {
    return null;
  }
}

// ── Summary artifact ─────────────────────────────────────────────────────────
// Emit both a human-readable stdout summary and a machine-readable JSON file
// (uploaded as a CI artifact by .github/workflows/load-test.yml).
export function handleSummary(data) {
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    "load-summary.json": JSON.stringify(data, null, 2),
  };
}
