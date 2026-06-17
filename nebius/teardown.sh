#!/usr/bin/env bash
# Destroy all billable Nebius Serverless resources.
# Run this after demos/judging to stop the billing clock.
# PostgreSQL and Object Storage are NOT destroyed (data must survive).
#
# Usage:
#   bash nebius/teardown.sh   # destroy both endpoints (analysis GPU + backend CPU)

set -euo pipefail

source "$(dirname "$0")/../.env"

echo "=== Archon Teardown ==="
echo "Project: $NEBIUS_PROJECT_ID"
echo ""

_delete_endpoint() {
    local NAME="$1"
    local STEP="$2"
    echo "[$STEP] Looking for endpoint '$NAME'..."

    ENDPOINT_ID=$(nebius ai endpoint list \
      --parent-id "$NEBIUS_PROJECT_ID" \
      --format json 2>/dev/null \
      | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for e in items:
    if e.get('metadata',{}).get('name') == '$NAME':
        print(e.get('metadata',{}).get('id','') or e.get('id',''))
        break
" 2>/dev/null || true)

    if [[ -n "$ENDPOINT_ID" ]]; then
        echo "    Found: $ENDPOINT_ID — deleting..."
        nebius ai endpoint delete "$ENDPOINT_ID" --parent-id "$NEBIUS_PROJECT_ID"
        echo "    Deleted. Billing stopped."
    else
        echo "    '$NAME' not found — already gone."
    fi
}

_delete_endpoint "archon-analysis" "1/2"
echo ""
_delete_endpoint "archon-backend"  "2/2"

echo ""
echo "=== Teardown complete ==="
echo "Still running (by design):"
echo "  - Nebius Managed PostgreSQL  (~\$0.14/hr — keep for data persistence)"
echo "  - Nebius Object Storage      (~\$0.00/hr — negligible)"
echo "  - Firebase Hosting           (free)"
echo ""
echo "To redeploy:  bash nebius/redeploy.sh"
