#!/usr/bin/env bash
# Deploy the Archon analysis container as a Nebius Serverless AI Endpoint.
# Run this once after pushing the analysis image.
# Docs: https://docs.nebius.com/serverless/endpoints/manage

set -euo pipefail

source "$(dirname "$0")/../.env"

ENDPOINT_NAME="archon-analysis"
TOKEN=$(openssl rand -hex 32)
echo "Generated endpoint token: $TOKEN"
echo "Save this — it will not be shown again."

nebius ai endpoint create \
  --name "$ENDPOINT_NAME" \
  --image "$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH/archon-analysis:latest" \
  --container-port 8001 \
  --platform gpu-l40s-a \
  --preset 1gpu-8vcpu-32gb \
  --public \
  --auth token \
  --token "$TOKEN" \
  --env "NEBIUS_BUCKET_NAME=$NEBIUS_BUCKET_NAME" \
  --env "STORAGE_ENDPOINT_URL=$STORAGE_ENDPOINT_URL" \
  --env "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" \
  --env "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" \
  --env "NEBIUS_INFERENCE_BASE_URL=$NEBIUS_INFERENCE_BASE_URL" \
  --env "NEBIUS_INFERENCE_API_KEY=$NEBIUS_INFERENCE_API_KEY" \
  --env "ANALYSIS_MODEL=${ANALYSIS_MODEL:-Qwen/Qwen2.5-72B-Instruct}"

echo ""
echo "Endpoint '$ENDPOINT_NAME' deployment started."
echo "Check status: nebius ai endpoint list"
echo "Update ANALYSIS_ENDPOINT_URL in .env once it reaches Running state."
