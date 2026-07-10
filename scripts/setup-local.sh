#!/usr/bin/env bash
# setup-local.sh — Single-command setup, launch, and E2E verification of Archon local stack.
#
# Usage:
#   bash scripts/setup-local.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Archon Local Environment Setup & Verification ==="

# 1. Environment file check
if [[ ! -f ".env" ]]; then
  echo "[1/5] Creating .env file from .env.example..."
  cp .env.example .env
else
  echo "[1/5] Found existing .env file."
fi

# Validate Inference API key is present
if grep -q "NEBIUS_INFERENCE_API_KEY=your-" .env || ! grep -q "NEBIUS_INFERENCE_API_KEY=" .env; then
  echo "⚠️  WARNING: NEBIUS_INFERENCE_API_KEY is not set or still set to the placeholder in .env."
  echo "   Extraction and analysis will fail until you provide a valid Nebius Inference API key."
  echo "   Please update your .env file with your key."
  echo ""
fi

# 2. Bring up the containers in background
echo "[2/5] Starting Docker Compose services (backend, frontend, localstack, extraction, analysis)..."
docker compose up --build -d

# 3. Wait for backend to be healthy
echo "[3/5] Waiting for backend API to become healthy..."
BACKEND_URL="http://localhost:8000"
HEALTHY=false
MAX_ATTEMPTS=60
for i in $(seq 1 $MAX_ATTEMPTS); do
  if curl -sf "$BACKEND_URL/health" >/dev/null 2>&1; then
    echo "    Backend is healthy!"
    HEALTHY=true
    break
  fi
  echo "    [$i/$MAX_ATTEMPTS] Waiting for backend..."
  sleep 2
done

if [[ "$HEALTHY" != "true" ]]; then
  echo "❌ ERROR: Backend service did not become healthy within 2 minutes."
  echo "   Check service logs with: docker compose logs"
  exit 1
fi

# 4. Generate sample PDF documents
echo "[4/5] Generating synthetic sample invoices and payroll documents..."
python scripts/generate-sample-data.py

# 5. Run the E2E verification test pipeline
echo "[5/5] Executing E2E test pipeline to verify extraction and analysis flow..."
if bash scripts/test-pipeline.sh; then
  echo ""
  echo "========================================================================"
  echo "✅ SETUP & E2E VERIFICATION COMPLETED SUCCESSFULLY!"
  echo "========================================================================"
  echo "The entire Archon stack is up and running."
  echo "  - Frontend Dashboard : http://localhost:3000"
  echo "  - Backend API        : http://localhost:8000/docs"
  echo "  - Local S3 (LocalStack): http://localhost:4566"
  echo ""
  echo "To view runtime logs:   docker compose logs -f"
  echo "To stop the services:   docker compose down"
  echo "========================================================================"
else
  echo ""
  echo "❌ E2E VERIFICATION FAILED!"
  echo "   Some services might not be configured properly or missing API keys."
  echo "   Check logs using: docker compose logs"
  exit 1
fi
