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
echo "[1/5] Health check..."
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

echo "[2/5] Uploading ${#INVOICE_FILES[@]} files..."
UPLOAD_RESP=$(curl -sf -X POST "$BASE_URL/api/upload" \
  -F "period=$PERIOD" \
  "${INVOICE_FILES[@]}")
echo "$UPLOAD_RESP" | python3 -m json.tool
UPLOAD_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['uploadId'])")
echo "Upload ID: $UPLOAD_ID"
echo ""

# 3. Submit extraction job
echo "[3/5] Submitting extraction job..."
JOB_RESP=$(curl -sf -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"uploadId\": \"$UPLOAD_ID\", \"period\": \"$PERIOD\"}")
echo "$JOB_RESP" | python3 -m json.tool
JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or d.get('jobId'))")
echo ""

# 4. Poll job status (max 5 min). Tolerant of transient network/parse blips:
#    a single failed poll must not abort the whole run under `set -e`.
echo "[4/5] Waiting for extraction job to complete..."
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
echo "[5/5] Triggering analysis (with retry)..."
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
echo "=== Smoke test complete ==="
echo "Open http://localhost:3000/dashboard/$PERIOD to view the dashboard."
