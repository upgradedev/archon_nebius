#!/usr/bin/env bash
# Full redeploy of Archon on Nebius: teardown → build → push → deploy endpoint.
# Images are only rebuilt if --build flag is passed; otherwise uses existing tags.
#
# Usage:
#   bash nebius/redeploy.sh           # redeploy endpoint with existing images
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

# ── Step 1: Teardown existing endpoint ────────────────────────────────────────
echo "[1/4] Tearing down existing endpoint..."
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
    echo "[3/4] Building and pushing images..."

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

    echo "  Images pushed."
else
    echo "[3/4] Skipping image build (pass --build to rebuild)."
fi
echo ""

# ── Step 4: Deploy analysis endpoint ──────────────────────────────────────────
echo "[4/4] Deploying analysis endpoint..."

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
echo "=== Redeploy complete ==="
echo ""
echo "Endpoint token (save to .env as ANALYSIS_ENDPOINT_TOKEN):"
echo "  $ENDPOINT_TOKEN"
echo ""
echo "Check status:    nebius ai endpoint list"
echo "Tear down when done:  bash nebius/teardown.sh"
echo ""
echo "Estimated cost while running:"
echo "  L40S endpoint:   ~\$0.90/hr"
echo "  H200 (if L40S unavailable): ~\$4.50/hr  ← CHECK PLATFORM BEFORE LEAVING ON"
