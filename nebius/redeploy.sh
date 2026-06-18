#!/usr/bin/env bash
# Full redeploy of Archon on Nebius: teardown → build → push → deploy.
#
# Architecture after this script:
#   archon-backend    — Nebius Serverless AI Endpoint (CPU, always-on orchestration)
#   archon-extraction — Nebius Serverless AI Job      (GPU L40S, on-demand per upload)
#   archon-analysis   — Nebius Serverless AI Job      (CPU, on-demand per analysis request)
#
# Images are only rebuilt if --build flag is passed; otherwise existing tags are reused.
#
# Usage:
#   bash nebius/redeploy.sh           # redeploy with existing images
#   bash nebius/redeploy.sh --build   # rebuild + push images, then deploy

set -euo pipefail

source "$(dirname "$0")/../.env"

BUILD=false
[[ "${1:-}" == "--build" ]] && BUILD=true

SCRIPT_DIR="$(dirname "$0")"
REGISTRY="$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH"

echo "=== Archon Redeploy ==="
echo "Project:  $NEBIUS_PROJECT_ID"
echo "Registry: $REGISTRY"
echo ""

# ── Step 1: Teardown existing endpoints ───────────────────────────────────────
echo "[1/4] Tearing down existing endpoints..."
bash "$SCRIPT_DIR/teardown.sh" || true   # non-fatal if nothing to tear down
echo ""

# ── Step 2: Verify GPU platform availability ───────────────────────────────────
echo "[2/4] Checking available GPU platforms..."
AVAILABLE_PLATFORMS=$(nebius ai endpoint platform list \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --format json 2>/dev/null \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for p in items:
    print(p.get('id','') or p.get('name',''))
" 2>/dev/null || echo "unknown")

echo "    Available: $AVAILABLE_PLATFORMS"

EXTRACTION_PLATFORM="${EXTRACTION_JOB_PLATFORM:-cpu-d3}"
EXTRACTION_PRESET="${EXTRACTION_JOB_PRESET:-4vcpu-16gb}"
echo ""

# ── Step 3: Build and push images (optional) ──────────────────────────────────
if [[ "$BUILD" == "true" ]]; then
    echo "[3/4] Building and pushing images..."

    # Docker login to Nebius CR
    IAM_TOKEN=$(nebius iam get-access-token 2>/dev/null || echo "$NEBIUS_IAM_TOKEN")
    echo "$IAM_TOKEN" | docker login "$NEBIUS_REGISTRY" --username iam --password-stdin

    # Extraction job image (GPU)
    echo "  Building archon-extraction..."
    docker build -t "$REGISTRY/archon-extraction:latest" \
      "$(dirname "$SCRIPT_DIR")/jobs/extraction"
    docker push "$REGISTRY/archon-extraction:latest"

    # Analysis job image (CPU)
    echo "  Building archon-analysis..."
    docker build -t "$REGISTRY/archon-analysis:latest" \
      "$(dirname "$SCRIPT_DIR")/jobs/analysis"
    docker push "$REGISTRY/archon-analysis:latest"

    # Backend endpoint image (CPU + HTTPS via Caddy)
    echo "  Building archon-backend..."
    docker build -f "$(dirname "$SCRIPT_DIR")/backend/Dockerfile.https" \
      -t "$REGISTRY/archon-backend:latest" \
      "$(dirname "$SCRIPT_DIR")/backend"
    docker push "$REGISTRY/archon-backend:latest"

    echo "  Images pushed."
else
    echo "[3/4] Skipping image build (pass --build to rebuild)."
fi
echo ""

# ── Step 4: Deploy backend endpoint (CPU, always-on) ──────────────────────────
echo "[4/4] Deploying backend endpoint (CPU)..."

nebius ai endpoint create \
  --name "archon-backend" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$REGISTRY/archon-backend:latest" \
  --container-port 443 \
  --platform cpu-d3 \
  --preset 4vcpu-16gb \
  --public \
  --env "NEBIUS_IAM_TOKEN=$NEBIUS_IAM_TOKEN" \
  --env "NEBIUS_PROJECT_ID=$NEBIUS_PROJECT_ID" \
  --env "NEBIUS_SUBNET_ID=${NEBIUS_SUBNET_ID:-}" \
  --env "NEBIUS_BUCKET_NAME=$NEBIUS_BUCKET_NAME" \
  --env "STORAGE_ENDPOINT_URL=$STORAGE_ENDPOINT_URL" \
  --env "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" \
  --env "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" \
  --env "POSTGRES_HOST=$POSTGRES_HOST" \
  --env "POSTGRES_PORT=$POSTGRES_PORT" \
  --env "POSTGRES_DB=$POSTGRES_DB" \
  --env "POSTGRES_USER=$POSTGRES_USER" \
  --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
  --env "NEBIUS_INFERENCE_BASE_URL=$NEBIUS_INFERENCE_BASE_URL" \
  --env "NEBIUS_INFERENCE_API_KEY=$NEBIUS_INFERENCE_API_KEY" \
  --env "EXTRACTION_JOB_IMAGE=$REGISTRY/archon-extraction:latest" \
  --env "EXTRACTION_JOB_PLATFORM=${EXTRACTION_JOB_PLATFORM:-cpu-d3}" \
  --env "EXTRACTION_JOB_PRESET=${EXTRACTION_JOB_PRESET:-4vcpu-16gb}" \
  --env "ANALYSIS_JOB_IMAGE=$REGISTRY/archon-analysis:latest" \
  --env "ANALYSIS_JOB_PLATFORM=${ANALYSIS_JOB_PLATFORM:-cpu-d3}" \
  --env "ANALYSIS_JOB_PRESET=${ANALYSIS_JOB_PRESET:-4vcpu-16gb}" \
  --env "CORS_ORIGINS=${CORS_ORIGINS:-https://archon-pnl.web.app,http://localhost:3000}" \
  --env "JOB_RUNNER_BACKEND=nebius" \
  --env "DUCKDNS_TOKEN=${DUCKDNS_TOKEN}" \
  --env "DUCKDNS_SUBDOMAIN=archon-api" \
  --env "CADDY_DOMAIN=archon-api.duckdns.org"

echo ""
echo "=== Redeploy complete ==="
echo ""
echo "Architecture (fully serverless — zero always-on GPU cost):"
echo "  Firebase Hosting    → React frontend (static CDN, free)"
echo "  archon-backend      → Nebius Serverless AI Endpoint (CPU cpu-d3/4vcpu-16gb, ~\$0.04/hr)"
echo "  archon-extraction   → Nebius Serverless AI Job      (CPU $EXTRACTION_PLATFORM/$EXTRACTION_PRESET, ~\$0.01/run — vision via Nebius Inference API)"
echo "  archon-analysis     → Nebius Serverless AI Job      (CPU cpu-d3/4vcpu-16gb, ~\$0.01/run)"
echo ""
echo "Check endpoint status:"
echo "  nebius ai endpoint list --parent-id $NEBIUS_PROJECT_ID"
echo ""
echo "Get backend public IP:"
echo "  nebius ai endpoint get --name archon-backend --parent-id $NEBIUS_PROJECT_ID --format json"
echo ""
echo "Tear down when done:  bash nebius/teardown.sh"
