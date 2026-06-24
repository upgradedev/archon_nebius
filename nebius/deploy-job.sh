#!/usr/bin/env bash
# One-shot test run of the extraction job on Nebius Serverless AI Jobs.
# In production, the backend submits jobs via the Python SDK / CLI.
# Docs: https://docs.nebius.com/serverless/jobs/manage
#
# Backward-compatible cookbook-aligned options (all optional, default = current behaviour):
#   <VAR>_SECRET   — if set for any env var, that var is passed via --env-secret
#                    (Nebius secret selector) instead of plaintext --env.
#                    Mirrors cookbook life-science/bionemo-agent/scripts/run_serverless_endpoint.sh.
#   PREEMPTIBLE=1  — request a preemptible (spot) instance for the job. Default: off.
#   JOB_TIMEOUT    — job timeout (default 2h). Always passed to Nebius.
#   IMAGE_DIGEST   — if set, the image is pinned as image@sha256:<digest> instead of :latest.
#                    Nebius DEVELOPER_GUIDE best practice: pin image digests for reproducible deploys.

set -euo pipefail

source "$(dirname "$0")/../.env"

UPLOAD_ID="${1:?Usage: deploy-job.sh <upload_id> <period>}"
PERIOD="${2:?Usage: deploy-job.sh <upload_id> <period>}"

JOB_NAME="archon-extract-$PERIOD-$(openssl rand -hex 3)"

# --- Image reference: pin to a digest if IMAGE_DIGEST is provided, else :latest -----------
# Best practice (Nebius DEVELOPER_GUIDE): deploy by immutable digest for reproducibility.
IMAGE_BASE="$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH/archon-extraction"
if [ -n "${IMAGE_DIGEST:-}" ]; then
  IMAGE_REF="${IMAGE_BASE}@${IMAGE_DIGEST}"
else
  IMAGE_REF="${IMAGE_BASE}:latest"
fi

# --- Env var emitter: plaintext --env by default, --env-secret if <VAR>_SECRET is set -------
# Usage: add_env VAR_NAME "$VAR_VALUE"
ENV_ARGS=()
add_env() {
  local name="$1"
  local value="$2"
  local secret_var="${name}_SECRET"
  local secret_ref="${!secret_var:-}"
  if [ -n "$secret_ref" ]; then
    ENV_ARGS+=(--env-secret "${name}=${secret_ref}")
  else
    ENV_ARGS+=(--env "${name}=${value}")
  fi
}

add_env UPLOAD_ID                 "$UPLOAD_ID"
add_env PERIOD                    "$PERIOD"
add_env NEBIUS_BUCKET_NAME        "$NEBIUS_BUCKET_NAME"
add_env STORAGE_ENDPOINT_URL      "$NEBIUS_STORAGE_ENDPOINT_URL"
add_env AWS_ACCESS_KEY_ID         "$NEBIUS_STORAGE_ACCESS_KEY_ID"
add_env AWS_SECRET_ACCESS_KEY     "$NEBIUS_STORAGE_SECRET_KEY"
add_env NEBIUS_INFERENCE_BASE_URL "$NEBIUS_INFERENCE_BASE_URL"
add_env NEBIUS_INFERENCE_API_KEY  "$NEBIUS_INFERENCE_API_KEY"
add_env VISION_MODEL              "${VISION_MODEL:-Qwen/Qwen2.5-VL-72B-Instruct}"

# --- Optional preemptible (spot) instance, gated behind PREEMPTIBLE (default off) -----------
PREEMPTIBLE_ARGS=()
if [ -n "${PREEMPTIBLE:-}" ] && [ "${PREEMPTIBLE}" != "0" ]; then
  PREEMPTIBLE_ARGS=(--preemptible)
  echo "Requesting a preemptible (spot) instance."
fi

nebius ai job create \
  --name "$JOB_NAME" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$IMAGE_REF" \
  --platform "${EXTRACTION_JOB_PLATFORM:-gpu-l40s-a}" \
  --preset "${EXTRACTION_JOB_PRESET:-1gpu-8vcpu-32gb}" \
  --timeout "${JOB_TIMEOUT:-2h}" \
  "${PREEMPTIBLE_ARGS[@]}" \
  "${ENV_ARGS[@]}"

echo "Job '$JOB_NAME' submitted. Monitor with: nebius ai job list"
# Retrieve job state / tail logs programmatically (cookbook jsonpath + logs pattern):
#   JOB_ID=$(nebius ai job list --format json | jq -r '.items[] | select(.metadata.name=="'"$JOB_NAME"'") | .metadata.id')
#   nebius ai job get "$JOB_ID" --format jsonpath='{.status.state}'
#   nebius ai job logs "$JOB_ID" --follow --timestamps
