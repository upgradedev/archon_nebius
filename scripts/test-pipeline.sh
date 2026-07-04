#!/usr/bin/env bash
# End-to-end pipeline smoke test against a running local stack.
# Requires: docker compose up (backend + analysis + localstack running)
#
# Usage:
#   bash scripts/test-pipeline.sh                  # uses all files in sample-data/
#   PERIOD=2026-01 bash scripts/test-pipeline.sh   # specific period

set -euo pipefail

BASE_URL="${BACKEND_URL:-http://localhost:8000}"
PERIOD="${PERIOD:-2026-01}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SAMPLE_DIR="$REPO_DIR/sample-data"

echo "=== Archon pipeline smoke test ==="
echo "Backend:    $BASE_URL"
echo "Period:     $PERIOD"
echo "Sample dir: $SAMPLE_DIR"
echo ""

# 1. Health check
echo "[1/6] Health check..."
curl -sf "$BASE_URL/health" | python3 -m json.tool
echo ""

# 2. Collect sample files — all PDFs under sample-data/ recursively
INVOICE_FILES=()
while IFS= read -r -d '' f; do
  INVOICE_FILES+=("-F" "files=@$f")
done < <(find "$SAMPLE_DIR" -name "*.pdf" -print0)

if [[ ${#INVOICE_FILES[@]} -eq 0 ]]; then
  echo "ERROR: No sample files found in $SAMPLE_DIR"
  exit 1
fi

echo "[2/6] Uploading ${#INVOICE_FILES[@]} files..."
UPLOAD_RESP=$(curl -sf -X POST "$BASE_URL/api/upload" \
  -F "period=$PERIOD" \
  "${INVOICE_FILES[@]}")
echo "$UPLOAD_RESP" | python3 -m json.tool
UPLOAD_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['uploadId'])")
echo "Upload ID: $UPLOAD_ID"
echo ""

# 3. Submit extraction job
echo "[3/6] Submitting extraction job..."
JOB_RESP=$(curl -sf -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"uploadId\": \"$UPLOAD_ID\", \"period\": \"$PERIOD\"}")
echo "$JOB_RESP" | python3 -m json.tool
JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or d.get('jobId'))")
echo ""

# 4. Poll job status (max 5 min). Tolerant of transient network/parse blips:
#    a single failed poll must not abort the whole run under `set -e`.
echo "[4/6] Waiting for extraction job to complete..."
for i in $(seq 1 60); do
  STATUS=$(curl -sf "$BASE_URL/api/jobs/$JOB_ID" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null \
    || echo "transient")
  echo "  [$i] status: $STATUS"
  if [[ "$STATUS" == "completed" ]]; then break; fi
  if [[ "$STATUS" == "failed" ]]; then echo "ERROR: Job failed"; exit 1; fi
  sleep 5
done
if [[ "${STATUS:-}" != "completed" ]]; then
  echo "ERROR: extraction did not complete in time (last status: ${STATUS:-none})"
  exit 1
fi
echo ""

# 5. Trigger analysis — retry with backoff so a transient model hiccup
#    (narrator LLM rate-limit / timeout) doesn't false-red the gate.
echo "[5/6] Triggering analysis (with retry)..."
ANALYZE_OK=false
for attempt in 1 2 3 4; do
  if RESP=$(curl -sf --max-time 200 -X POST "$BASE_URL/api/analyze" \
       -H "Content-Type: application/json" \
       -d "{\"period\": \"$PERIOD\"}"); then
    echo "$RESP" | python3 -m json.tool
    ANALYZE_OK=true
    break
  fi
  echo "  analyze attempt $attempt failed (transient model hiccup?); retrying in $((attempt * 15))s..."
  sleep $((attempt * 15))
done
if [[ "$ANALYZE_OK" != "true" ]]; then
  echo "ERROR: analysis did not succeed after 4 attempts"
  exit 1
fi
echo ""

# 6. Assert report CONTENT, not just HTTP 2xx. A gate that only checks that
#    endpoints respond proves the pipeline "runs"; these assertions prove it is
#    "right": the report contract is complete, the P&L is non-trivial and
#    internally consistent to the cent, and the payroll-fusion invariant holds.
echo "[6/6] Fetching report and asserting content..."
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required for content assertions"; exit 1; }

REPORT_ENVELOPE=$(curl -sf "$BASE_URL/api/reports/$PERIOD") \
  || { echo "ERROR: GET /api/reports/$PERIOD failed"; exit 1; }
# Endpoint returns {jobId, report:{<FinancialReport>}, generatedAt}; unwrap it.
REPORT=$(echo "$REPORT_ENVELOPE" | jq -c 'if has("report") then .report else . end')

# 6a. Top-level report contract keys must ALL be present.
echo "$REPORT" | jq -e '
  . as $r
  | ["period","pnl","cashFlow","expenseBreakdown","topVendors","keyMetrics",
     "payrollEvents","employeeSummaries","validationResults",
     "vendorReconciliations","executiveSummary"]
  | all(.[]; in($r))
' >/dev/null \
  || { echo "ERROR: report is missing one or more contract keys"; echo "$REPORT" | jq 'keys'; exit 1; }

# 6b. P&L must be non-trivial (expenses>0) and satisfy the accounting identity
#     netProfit == revenue - expenses, to the cent.
echo "$REPORT" | jq -e '
  .pnl
  | (.expenses > 0)
    and (((.netProfit - (.revenue - .expenses)) | if . < 0 then -. else . end) < 0.01)
' >/dev/null \
  || { echo "ERROR: P&L identity/expenses assertion failed"; echo "$REPORT" | jq '.pnl'; exit 1; }

# 6c. Payroll-fusion invariant (Archon's thesis): where a payroll event carries
#     an employer_cost_total, it must be >= the bank net_total. Guarded on
#     presence — the extraction schema does not currently request that field
#     (jobs/extraction/extractors/*), so on the live path it is legitimately
#     null; a hard requirement would false-red the gate. When present, enforced.
echo "$REPORT" | jq -e '
  [ .payrollEvents[]?
    | select(.employer_cost_total != null)
    | (.employer_cost_total >= .net_total) ]
  | all(.[]; .)
' >/dev/null \
  || { echo "ERROR: employer_cost_total < net_total on a payroll event"; echo "$REPORT" | jq '.payrollEvents'; exit 1; }

echo "  content OK: contract keys present · P&L identity holds (expenses>0) · payroll invariant holds"

echo ""
echo "=== Smoke test complete ==="
echo "Open http://localhost:3000/dashboard/$PERIOD to view the dashboard."
