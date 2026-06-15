#!/usr/bin/env bash
# Deploy the Archon analysis container as a Nebius Serverless AI Endpoint.
# Run this once after pushing the analysis image.
# Docs: https://docs.nebius.com/serverless/endpoints/manage

set -euo pipefail

source "$(dirname "$0")/../.env"

ENDPOINT_NAME="archon-analysis"
ENDPOINT_TOKEN=$(openssl rand -hex 32)
echo "Generated endpoint token: $ENDPOINT_TOKEN"
echo "Save this — you will need it as ANALYSIS_ENDPOINT_TOKEN in your .env."

# Guard: L40S = ~$0.90/hr | H200 (region default if L40S unavailable) = ~$4.50/hr
echo ""
echo "⚠  COST CHECK: verify L40S is available before proceeding."
echo "   Run: nebius ai endpoint platform list"
echo "   Press Ctrl+C to abort, or Enter to continue."
read -r

nebius ai endpoint create \
  --name "$ENDPOINT_NAME" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH/archon-analysis:latest" \
  --container-port 8001 \
  --platform gpu-l40s-a \
  --preset 1gpu-8vcpu-32gb \
  --public \
  --auth token \
  --token "$ENDPOINT_TOKEN" \
  --env "NEBIUS_BUCKET_NAME=$NEBIUS_BUCKET_NAME" \
  --env "STORAGE_ENDPOINT_URL=$NEBIUS_STORAGE_ENDPOINT_URL" \
  --env "AWS_ACCESS_KEY_ID=$NEBIUS_STORAGE_ACCESS_KEY_ID" \
  --env "AWS_SECRET_ACCESS_KEY=$NEBIUS_STORAGE_SECRET_KEY" \
  --env "NEBIUS_INFERENCE_BASE_URL=$NEBIUS_INFERENCE_BASE_URL" \
  --env "NEBIUS_INFERENCE_API_KEY=$NEBIUS_INFERENCE_API_KEY" \
  --env "ANALYSIS_MODEL=${ANALYSIS_MODEL:-meta-llama/Llama-3.3-70B-Instruct}"

echo ""
echo "Endpoint '$ENDPOINT_NAME' deployment started."
echo "Check status:  nebius ai endpoint list"
echo "Once RUNNING, update ANALYSIS_ENDPOINT_URL in .env with the endpoint URL."
