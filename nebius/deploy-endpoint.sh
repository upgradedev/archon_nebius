#!/usr/bin/env bash
# Deploy the Archon analysis container as a Nebius Serverless AI Endpoint.
# Run this once after pushing the analysis image.
# Docs: https://docs.nebius.com/serverless/endpoints/manage
#
# Backward-compatible cookbook-aligned options (all optional, default = current behaviour):
#   <VAR>_SECRET   — if set for any env var, that var is passed via --env-secret
#                    (Nebius secret selector) instead of plaintext --env.
#                    Mirrors cookbook life-science/bionemo-agent/scripts/run_serverless_endpoint.sh.
#   ENDPOINT_TOKEN_SECRET — if set, the auth token is passed via --token-secret instead of --token.
#   IMAGE_DIGEST   — if set, the image is pinned as image@sha256:<digest> instead of :latest.
#                    Nebius DEVELOPER_GUIDE best practice: pin image digests for reproducible deploys.

set -euo pipefail

source "$(dirname "$0")/../.env"

ENDPOINT_NAME="archon-analysis"

# --- Image reference: pin to a digest if IMAGE_DIGEST is provided, else :latest -----------
# Best practice (Nebius DEVELOPER_GUIDE): deploy by immutable digest for reproducibility.
IMAGE_BASE="$NEBIUS_REGISTRY/$NEBIUS_REGISTRY_PATH/archon-analysis"
if [ -n "${IMAGE_DIGEST:-}" ]; then
  IMAGE_REF="${IMAGE_BASE}@${IMAGE_DIGEST}"
else
  IMAGE_REF="${IMAGE_BASE}:latest"
fi

# --- Auth token: plaintext --token by default, --token-secret if a secret selector is set --
if [ -n "${ENDPOINT_TOKEN_SECRET:-}" ]; then
  TOKEN_ARGS=(--token-secret "$ENDPOINT_TOKEN_SECRET")
  echo "Using token secret selector: $ENDPOINT_TOKEN_SECRET"
else
  ENDPOINT_TOKEN=$(openssl rand -hex 32)
  TOKEN_ARGS=(--token "$ENDPOINT_TOKEN")
  echo "Generated endpoint token: $ENDPOINT_TOKEN"
  echo "Save this — you will need it as ANALYSIS_ENDPOINT_TOKEN in your .env."
fi

# --- Env var emitter: plaintext --env by default, --env-secret if <VAR>_SECRET is set -------
# Usage: add_env VAR_NAME "$VAR_VALUE"
# If a variable named <VAR_NAME>_SECRET is set in the environment, the value is sourced from
# the Nebius secret of that name via --env-secret; otherwise the plaintext value is passed.
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

add_env NEBIUS_BUCKET_NAME        "$NEBIUS_BUCKET_NAME"
add_env STORAGE_ENDPOINT_URL      "$NEBIUS_STORAGE_ENDPOINT_URL"
add_env AWS_ACCESS_KEY_ID         "$NEBIUS_STORAGE_ACCESS_KEY_ID"
add_env AWS_SECRET_ACCESS_KEY     "$NEBIUS_STORAGE_SECRET_KEY"
add_env NEBIUS_INFERENCE_BASE_URL "$NEBIUS_INFERENCE_BASE_URL"
add_env NEBIUS_INFERENCE_API_KEY  "$NEBIUS_INFERENCE_API_KEY"
add_env ANALYSIS_MODEL            "${ANALYSIS_MODEL:-meta-llama/Llama-3.3-70B-Instruct}"

# Guard: L40S = ~$0.90/hr | H200 (region default if L40S unavailable) = ~$4.50/hr
echo ""
echo "⚠  COST CHECK: verify L40S is available before proceeding."
echo "   Run: nebius ai endpoint platform list"
echo "   Press Ctrl+C to abort, or Enter to continue."
read -r

nebius ai endpoint create \
  --name "$ENDPOINT_NAME" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --image "$IMAGE_REF" \
  --container-port 8001 \
  --platform gpu-l40s-a \
  --preset 1gpu-8vcpu-32gb \
  --public \
  --auth token \
  "${TOKEN_ARGS[@]}" \
  "${ENV_ARGS[@]}"

echo ""
echo "Endpoint '$ENDPOINT_NAME' deployment started."
echo "Check status:  nebius ai endpoint list"

# Retrieve the public endpoint URL programmatically (cookbook jsonpath pattern):
#   ENDPOINT_ID=$(nebius ai endpoint list --format json | jq -r '.items[] | select(.metadata.name=="'"$ENDPOINT_NAME"'") | .metadata.id')
#   nebius ai endpoint get "$ENDPOINT_ID" --format jsonpath='{.status.public_endpoints[0]}'
# Tail logs:
#   nebius ai endpoint logs "$ENDPOINT_ID" --follow --timestamps
echo "Once RUNNING, update ANALYSIS_ENDPOINT_URL in .env with the endpoint URL."
echo "  Get URL:  nebius ai endpoint get <ID> --format jsonpath='{.status.public_endpoints[0]}'"
echo "  Tail logs: nebius ai endpoint logs <ID> --follow --timestamps"
