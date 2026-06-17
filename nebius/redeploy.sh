#!/usr/bin/env bash
# Full redeploy of Archon on Nebius: teardown → build → push → deploy.
# Deploys two Nebius Serverless AI Endpoints (analysis GPU + backend CPU)
# and relies on Nebius Serverless AI Jobs for extraction (on-demand GPU).
# Images are only rebuilt if --build flag is passed; otherwise uses existing tags.
#
# Usage:
#   bash nebius/redeploy.sh           # redeploy with existing images
#   bash nebius/redeploy.sh --build   # rebuild + push images, then deploy

set -euo pipefail

source "$(dirname "$0")/../.env"

BUILD=false
[[ "${1:-}" == "--build" ]] && BUILD=true

SCRIPT_DIR="$(dirname "$0")"
REGISTRY="$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PROJECT"

echo "=== Archon Redeploy ==="
echo "Project:  $NEBIUS_PROJECT_ID"
echo "Registry: $REGISTRY"
echo ""

# ── Step 1: Teardown existing endpoints ───────────────────────────────────────
echo "[1/5] Tearing down existing endpoints..."
bash "$SCRIPT_DIR/teardown.sh" || true   # non-fatal if nothing to tear down
echo ""

# ── Step 2: Verify GPU platform availability ───────────────────────────────────
echo "[2/5] Checking available GPU platforms..."
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

PLATFORM="gpu-l40s-a"
PRESET="1gpu-8vcpu-32gb"

# Warn if L40S is not listed — H200 will be 5x more expensive
if [[ "$AVAILABLE_PLATFORMS" != "unknown" ]] && ! echo "$AVAILABLE_PLATFORMS" | grep -q "l40s"; then
    echo ""
    echo "  ⚠  WARNING: gpu-l40s-a not listed as available in eu-west1."
    echo "     Nebius may silently assign H200 NVLink (~\$4.50/hr vs \$0.90/hr for L40S)."
    echo "     Press Ctrl+C to abort, or Enter to continue anyway."
    read -r
fi
echo ""

# ── Step 3: Build and push images (optional) ──────────────────────────────────
if [[ "$BUILD" == "true" ]]; then
    echo "[3/5] Building and pushing images..."

    # Docker login to Nebius CR
    IAM_TOKEN=$(nebius iam get-access-token 2>/dev/null || echo "$NEBIUS_IAM_TOKEN")
    echo "$IAM_TOKEN" | docker login "$NEBIUS_REGISTRY" --username iam --password-stdin

    # Analysis endpoint image
    echo "  Building archon-analysis..."
    docker build -t "$REGISTRY/archon-analysis:latest" \
      "$(dirname "$SCRIPT_DIR")/endpoints/analysis"
    docker push "$REGISTRY/archon-analysis:latest"

    # Extraction job image
    echo "  Building archon-extraction..."
    docker build -t "$REGISTRY/archon-extraction:latest" \
      "$(dirname "$SCRIPT_DIR")/jobs/extraction"
    docker push "$REGISTRY/archon-extraction:latest"

    # Backend endpoint image
    echo "  Building archon-backend..."
    docker build -t "$REGISTRY/archon-backend:latest" \
      "$(dirname "$SCRIPT_DIR")/backend"
    docker push "$REGISTRY/archon-backend:latest"

    echo "  Images pushed."
else
    echo "[3/5] Skipping image build (pass --build to rebuild)."
fi
echo ""

# ── Step 4: Deploy analysis endpoint (GPU L40S) ────────────────────────────────
echo "[4/5] Deploying analysis endpoint (GPU)..."

ENDPOINT_TOKEN=$(openssl rand -hex 32)

nebius ai endpoint create \
  --name "archon-analysis" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$REGISTRY/archon-analysis:latest" \
  --container-port 8001 \
  --platform "$PLATFORM" \
  --preset "$PRESET" \
  --public \
  --auth token \
  --token "$ENDPOINT_TOKEN" \
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
  --env "ANALYSIS_MODEL=${ANALYSIS_MODEL:-meta-llama/Llama-3.3-70B-Instruct}"

echo ""

# ── Step 5: Deploy backend endpoint (CPU) ─────────────────────────────────────
echo "[5/5] Deploying backend endpoint (CPU)..."

# Fetch analysis endpoint public IP to pass as ANALYSIS_ENDPOINT_URL
echo "    Waiting for analysis endpoint to get a public IP..."
for i in $(seq 1 20); do
    ANALYSIS_IP=$(nebius ai endpoint list \
      --parent-id "$NEBIUS_PROJECT_ID" \
      --format json 2>/dev/null \
      | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for e in items:
    if e.get('metadata',{}).get('name') == 'archon-analysis':
        eps = e.get('status',{}).get('public_endpoints',[])
        if eps:
            print(eps[0])
        break
" 2>/dev/null || true)
    if [[ -n "$ANALYSIS_IP" ]]; then
        break
    fi
    sleep 15
done

ANALYSIS_ENDPOINT_URL="http://${ANALYSIS_IP:-placeholder}"

nebius ai endpoint create \
  --name "archon-backend" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$REGISTRY/archon-backend:latest" \
  --container-port 8000 \
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
  --env "ANALYSIS_ENDPOINT_URL=$ANALYSIS_ENDPOINT_URL" \
  --env "ANALYSIS_ENDPOINT_TOKEN=$ENDPOINT_TOKEN" \
  --env "EXTRACTION_JOB_IMAGE=$EXTRACTION_JOB_IMAGE" \
  --env "EXTRACTION_JOB_PLATFORM=${EXTRACTION_JOB_PLATFORM:-gpu-l40s-a}" \
  --env "EXTRACTION_JOB_PRESET=${EXTRACTION_JOB_PRESET:-1gpu-8vcpu-32gb}" \
  --env "CORS_ORIGINS=${CORS_ORIGINS:-https://archon-pnl.web.app,http://localhost:3000}" \
  --env "JOB_RUNNER_BACKEND=nebius"

echo ""
echo "=== Redeploy complete ==="
echo ""
echo "Architecture:"
echo "  Firebase Hosting  → React frontend (static CDN)"
echo "  archon-backend    → Nebius Serverless AI Endpoint (CPU cpu-d3/4vcpu-16gb)"
echo "  archon-analysis   → Nebius Serverless AI Endpoint (GPU $PLATFORM/$PRESET)"
echo "  archon-extraction → Nebius Serverless AI Job      (GPU $PLATFORM/$PRESET, on-demand)"
echo ""
echo "Analysis endpoint token (save to .env as ANALYSIS_ENDPOINT_TOKEN):"
echo "  $ENDPOINT_TOKEN"
echo ""
echo "Check endpoint status:"
echo "  nebius ai endpoint list --parent-id $NEBIUS_PROJECT_ID"
echo ""
echo "Get backend public IP:"
echo "  nebius ai endpoint get-by-name --name archon-backend --format jsonpath='{.status.public_endpoints[0]}'"
echo ""
echo "Estimated cost while running:"
echo "  CPU backend endpoint: ~\$0.04/hr  (cpu-d3/4vcpu-16gb)"
echo "  GPU analysis endpoint: ~\$0.90/hr (L40S)"
echo "  GPU extraction jobs:  ~\$0.15/run (on-demand, billed only when running)"
echo ""
echo "Tear down when done:  bash nebius/teardown.sh"
