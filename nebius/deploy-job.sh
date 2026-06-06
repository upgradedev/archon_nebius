#!/usr/bin/env bash
# One-shot test run of the extraction job on Nebius Serverless AI Jobs.
# In production, the backend submits jobs via the Python SDK / CLI.
# Docs: https://docs.nebius.com/serverless/jobs/manage

set -euo pipefail

source "$(dirname "$0")/../.env"

UPLOAD_ID="${1:?Usage: deploy-job.sh <upload_id> <period>}"
PERIOD="${2:?Usage: deploy-job.sh <upload_id> <period>}"

JOB_NAME="archon-extract-$PERIOD-$(openssl rand -hex 3)"

nebius ai job create \
  --name "$JOB_NAME" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH/archon-extraction:latest" \
  --platform "${EXTRACTION_JOB_PLATFORM:-gpu-l40s-a}" \
  --preset "${EXTRACTION_JOB_PRESET:-1gpu-8vcpu-32gb}" \
  --timeout 2h \
  --env "UPLOAD_ID=$UPLOAD_ID" \
  --env "PERIOD=$PERIOD" \
  --env "NEBIUS_BUCKET_NAME=$NEBIUS_BUCKET_NAME" \
  --env "STORAGE_ENDPOINT_URL=$NEBIUS_STORAGE_ENDPOINT_URL" \
  --env "AWS_ACCESS_KEY_ID=$NEBIUS_STORAGE_ACCESS_KEY_ID" \
  --env "AWS_SECRET_ACCESS_KEY=$NEBIUS_STORAGE_SECRET_KEY" \
  --env "NEBIUS_INFERENCE_BASE_URL=$NEBIUS_INFERENCE_BASE_URL" \
  --env "NEBIUS_INFERENCE_API_KEY=$NEBIUS_INFERENCE_API_KEY" \
  --env "VISION_MODEL=${VISION_MODEL:-Qwen/Qwen2.5-VL-72B-Instruct}"

echo "Job '$JOB_NAME' submitted. Monitor with: nebius ai job list"
