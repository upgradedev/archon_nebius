#!/usr/bin/env bash
# Full redeploy of Archon on Nebius: teardown → build → push → deploy.
#
# Architecture after this script:
#   archon-backend    — Nebius Serverless AI Endpoint (CPU, always-on orchestration)
#   archon-extraction — Nebius Serverless AI Job      (CPU, on-demand per upload; vision via Inference API)
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
# RUNTIME_IAM_TOKEN is used ONLY for `docker login` (image push) and CLI calls
# during this deploy. It is a short-lived (~12h) USER token and is deliberately
# NOT baked into the endpoint env — the endpoint authenticates at runtime with the
# service account (NEBIUS_SA_*), which never expires. See _make_sdk()/_get_registry_token().
RUNTIME_IAM_TOKEN=$(nebius iam get-access-token 2>/dev/null || echo "${NEBIUS_IAM_TOKEN:-}")

if [[ -z "${RUNTIME_IAM_TOKEN:-}" ]]; then
    echo "ERROR: could not obtain a Nebius IAM token. Run 'nebius iam get-access-token' or set NEBIUS_IAM_TOKEN." >&2
    exit 1
fi

# The endpoint's runtime identity is the service account. Refuse to deploy without
# it, otherwise the endpoint would have no durable credential for job submission /
# registry pull (we no longer fall back to baking the ~12h user token as a runtime env).
if [[ -z "${NEBIUS_SA_ID:-}" || -z "${NEBIUS_SA_KEY_ID:-}" || -z "${NEBIUS_SA_KEY_B64:-}" ]]; then
    echo "ERROR: NEBIUS_SA_ID / NEBIUS_SA_KEY_ID / NEBIUS_SA_KEY_B64 must be set in .env." >&2
    echo "       The backend endpoint authenticates via the service account (durable), not the user IAM token." >&2
    exit 1
fi

echo "=== Archon Redeploy ==="
echo "Project:  $NEBIUS_PROJECT_ID"
echo "Registry: $REGISTRY"
echo ""

# ── Step 1: Teardown existing endpoints ───────────────────────────────────────
echo "[1/4] Tearing down existing endpoints..."
bash "$SCRIPT_DIR/teardown.sh" || true   # non-fatal if nothing to tear down
echo ""

# ── Step 2: Verify endpoint API access ─────────────────────────────────────────
echo "[2/4] Checking Nebius endpoint API access..."
if nebius ai endpoint list --parent-id "$NEBIUS_PROJECT_ID" --format json >/tmp/nebius-endpoints.json 2>/tmp/nebius-endpoints.err; then
  echo "    Endpoint API access OK."
else
  echo "    Endpoint API access failed:"
  cat /tmp/nebius-endpoints.err
  exit 1
fi

EXTRACTION_PLATFORM="${EXTRACTION_JOB_PLATFORM:-cpu-d3}"
EXTRACTION_PRESET="${EXTRACTION_JOB_PRESET:-4vcpu-16gb}"
echo ""

# ── Step 3: Build and push images (optional) ──────────────────────────────────
if [[ "$BUILD" == "true" ]]; then
    echo "[3/4] Building and pushing images..."

    # Docker login to Nebius CR
    echo "$RUNTIME_IAM_TOKEN" | docker login "$NEBIUS_REGISTRY" --username iam --password-stdin

    # Extraction job image (CPU; vision LLM called over the Nebius Inference API)
    echo "  Building archon-extraction..."
    docker build -t "$REGISTRY/archon-extraction:latest" \
      "$(dirname "$SCRIPT_DIR")/jobs/extraction"
    docker push "$REGISTRY/archon-extraction:latest"

    # Analysis job image (CPU)
    echo "  Building archon-analysis..."
    docker build -t "$REGISTRY/archon-analysis:latest" \
      "$(dirname "$SCRIPT_DIR")/jobs/analysis"
    docker push "$REGISTRY/archon-analysis:latest"

    # Backend endpoint image: plain uvicorn on 8000. Nebius terminates TLS at the
    # Endpoint's managed HTTPS URL, so there is no in-container Caddy/DuckDNS/self-
    # signed cert. The LIVE path is the Firebase BFF (frontend/functions/main.py) →
    # the managed HTTPS URL (verify=True), which is read from status.public_endpoints
    # below. Build context is the REPO ROOT so the image also carries the job
    # pipelines for JOB_RUNNER_BACKEND=inline.
    echo "  Building archon-backend..."
    docker build -f "$(dirname "$SCRIPT_DIR")/backend/Dockerfile.endpoint" \
      -t "$REGISTRY/archon-backend:latest" \
      "$(dirname "$SCRIPT_DIR")"
    docker push "$REGISTRY/archon-backend:latest"

    echo "  Images pushed."
else
    echo "[3/4] Skipping image build (pass --build to rebuild)."
fi
echo ""

# ── Step 4: Deploy backend endpoint (CPU, always-on) ──────────────────────────
echo "[4/4] Deploying backend endpoint (CPU)..."

if [[ -z "${NEBIUS_REGISTRY_PASSWORD:-}" ]]; then
  echo "WARNING: NEBIUS_REGISTRY_PASSWORD is not set in .env."
  echo "         Falling back to temporary RUNTIME_IAM_TOKEN."
  echo "         ⚠️  The deployed endpoint will enter an 'error' state after 12 hours"
  echo "            if restarted or scaled, because this token will expire."
  echo "         To fix this permanently, issue a static key for CONTAINER_REGISTRY"
  echo "         on your service account ($NEBIUS_SA_ID) and set it as NEBIUS_REGISTRY_PASSWORD in .env."
  echo "         Command to generate:"
  echo "           nebius iam static-key issue --account-service-account-id=$NEBIUS_SA_ID --service=CONTAINER_REGISTRY"
  echo ""
fi

nebius ai endpoint create \
  --name "archon-backend" \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --subnet-id "$NEBIUS_SUBNET_ID" \
  --image "$REGISTRY/archon-backend:latest" \
  --container-port 8000 \
  --platform cpu-d3 \
  --preset 4vcpu-16gb \
  --registry-username iam \
  --registry-password "${NEBIUS_REGISTRY_PASSWORD:-$RUNTIME_IAM_TOKEN}" \
  --env "NEBIUS_SA_KEY_B64=${NEBIUS_SA_KEY_B64:-}" \
  --env "NEBIUS_SA_KEY_ID=${NEBIUS_SA_KEY_ID:-}" \
  --env "NEBIUS_SA_ID=${NEBIUS_SA_ID:-}" \
  --env "NEBIUS_PROJECT_ID=$NEBIUS_PROJECT_ID" \
  --env "NEBIUS_SUBNET_ID=${NEBIUS_SUBNET_ID:-}" \
  --env "NEBIUS_BUCKET_NAME=$NEBIUS_BUCKET_NAME" \
  --env "STORAGE_ENDPOINT_URL=${NEBIUS_STORAGE_ENDPOINT_URL:-$STORAGE_ENDPOINT_URL}" \
  --env "AWS_ACCESS_KEY_ID=${NEBIUS_STORAGE_ACCESS_KEY_ID:-$AWS_ACCESS_KEY_ID}" \
  --env "AWS_SECRET_ACCESS_KEY=${NEBIUS_STORAGE_SECRET_KEY:-$AWS_SECRET_ACCESS_KEY}" \
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
  --env "DOC_ENCRYPTION_ENABLED=${DOC_ENCRYPTION_ENABLED:-false}" \
  --env "DOC_ENCRYPTION_KMS_KEY_ID=${DOC_ENCRYPTION_KMS_KEY_ID:-}" \
  --env "NEBIUS_PROJECT_ID_LADDER=${NEBIUS_PROJECT_ID_LADDER:-}"

# ── Step 4: Read the endpoint's managed HTTPS URL ──────────────────────────────
# A Serverless Endpoint's HTTP container port is exposed through a platform-managed
# HTTPS URL in status.public_endpoints (trusted cert — no DuckDNS/Caddy). Newer
# endpoints show `https://<host>`; some legacy endpoints show `IP:port` instead, so
# accept either and normalise to an https:// URL. Set the result as NEBIUS_BACKEND_URL
# on the Firebase function so the BFF forwards /api/** to it.
echo "[4/4] Reading the endpoint's managed HTTPS URL..."
BACKEND_URL=""
for _ in $(seq 1 40); do
  BACKEND_URL=$(nebius ai endpoint get-by-name --name archon-backend \
    --parent-id "$NEBIUS_PROJECT_ID" --format json 2>/dev/null \
    | python3 -c "
import sys, json, re
d = json.load(sys.stdin)
for pe in d.get('status', {}).get('public_endpoints', []) or []:
    pe = str(pe).strip()
    if pe.startswith('http://') or pe.startswith('https://'):
        print(pe.rstrip('/')); break
    if re.match(r'^[0-9.]+:\d+$', pe):
        print('https://' + pe.split(':')[0]); break
" 2>/dev/null || echo "")
  [[ -n "$BACKEND_URL" ]] && break
  sleep 3
done
if [[ -n "$BACKEND_URL" ]]; then
  echo "    Managed backend URL: $BACKEND_URL"
  echo "    → set it on the Firebase function:  NEBIUS_BACKEND_URL=$BACKEND_URL"
else
  echo "    WARNING: could not read the endpoint's public URL yet; check 'nebius ai endpoint get-by-name --name archon-backend --format json' → status.public_endpoints." >&2
fi

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
echo "Get backend managed HTTPS URL (status.public_endpoints):"
echo "  nebius ai endpoint get --name archon-backend --parent-id $NEBIUS_PROJECT_ID --format json"
echo ""
echo "Tear down when done:  bash nebius/teardown.sh"
