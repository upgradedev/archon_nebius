#!/usr/bin/env bash
# End-to-end pipeline smoke test against a running local stack.
# Requires: docker compose up (backend + analysis + localstack running)

set -euo pipefail

BASE_URL="${BACKEND_URL:-http://localhost:8000}"
PERIOD="2026-04"

echo "=== Archon pipeline smoke test ==="
echo "Backend: $BASE_URL"
echo "Period:  $PERIOD"
echo ""

# 1. Health check
echo "[1/4] Health check..."
curl -sf "$BASE_URL/health" | python3 -m json.tool
echo ""

# 2. Upload sample docs
echo "[2/4] Uploading sample documents..."
UPLOAD_RESP=$(curl -sf -X POST "$BASE_URL/api/upload" \
  -F "period=$PERIOD" \
  -F "files=@sample-data/invoices/invoice_1_1.pdf" \
  -F "files=@sample-data/payroll/payroll_2026_04.pdf")
echo "$UPLOAD_RESP" | python3 -m json.tool
UPLOAD_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['uploadId'])")
echo "Upload ID: $UPLOAD_ID"
echo ""

# 3. Submit extraction job (NOTE: in local dev this is mocked — jobs run in docker)
echo "[3/4] Submitting extraction job..."
echo "(In local dev mode, extraction runs inside the docker analysis container)"
echo ""

# 4. Trigger analysis
echo "[4/4] Triggering analysis..."
curl -sf -X POST "$BASE_URL/api/analyze" \
  -H "Content-Type: application/json" \
  -d "{\"period\": \"$PERIOD\"}" | python3 -m json.tool

echo ""
echo "=== Smoke test complete ==="
echo "Open http://localhost:3000/dashboard/$PERIOD to view the dashboard."
