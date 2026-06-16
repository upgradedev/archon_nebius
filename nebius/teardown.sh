#!/usr/bin/env bash
# Destroy all billable Nebius GPU resources (endpoint + backend VM).
# Run this after demos/judging to stop the billing clock.
# PostgreSQL and Object Storage are NOT destroyed (data must survive).
#
# Usage:
#   bash nebius/teardown.sh            # destroy endpoint only
#   bash nebius/teardown.sh --all      # destroy endpoint + backend VM

set -euo pipefail

source "$(dirname "$0")/../.env"

ALL=false
[[ "${1:-}" == "--all" ]] && ALL=true

echo "=== Archon Teardown ==="
echo "Project: $NEBIUS_PROJECT_ID"
echo ""

# ── Delete analysis endpoint ──────────────────────────────────────────────────
echo "[1/2] Looking for endpoint 'archon-analysis'..."

ENDPOINT_ID=$(nebius ai endpoint list \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --format json 2>/dev/null \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for e in items:
    if e.get('metadata',{}).get('name') == 'archon-analysis':
        print(e.get('metadata',{}).get('id','') or e.get('id',''))
        break
" 2>/dev/null || true)

if [[ -n "$ENDPOINT_ID" ]]; then
    echo "    Found endpoint: $ENDPOINT_ID — deleting..."
    nebius ai endpoint delete "$ENDPOINT_ID" --parent-id "$NEBIUS_PROJECT_ID"
    echo "    Endpoint deleted. GPU billing stopped."
else
    echo "    No 'archon-analysis' endpoint found — already gone."
fi

# ── Stop backend VM (optional) ────────────────────────────────────────────────
if [[ "$ALL" == "true" ]]; then
    echo ""
    echo "[2/2] Looking for backend VM..."
    VM_ID=$(nebius compute instance list \
      --parent-id "$NEBIUS_PROJECT_ID" \
      --format json 2>/dev/null \
      | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for v in items:
    name = v.get('metadata',{}).get('name','')
    if 'archon' in name or 'backend' in name:
        print(v.get('metadata',{}).get('id','') or v.get('id',''))
        break
" 2>/dev/null || true)

    if [[ -n "$VM_ID" ]]; then
        echo "    Found VM: $VM_ID — stopping..."
        nebius compute instance stop "$VM_ID"
        echo "    VM stopped."
    else
        echo "    No archon VM found (may not exist or already stopped)."
    fi
else
    echo "[2/2] Skipping VM (pass --all to also stop the backend VM)."
fi

echo ""
echo "=== Teardown complete ==="
echo "Still running (by design):"
echo "  - Nebius Managed PostgreSQL  (~\$0.14/hr — keep for data persistence)"
echo "  - Nebius Object Storage      (~\$0.00/hr — negligible)"
echo "  - Firebase Hosting           (free)"
echo ""
echo "To redeploy:  bash nebius/redeploy.sh"
