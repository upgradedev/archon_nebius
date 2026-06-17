#!/bin/sh
set -e

# Update DuckDNS record to this container's public IP on startup
if [ -n "$DUCKDNS_TOKEN" ] && [ -n "$DUCKDNS_SUBDOMAIN" ]; then
  IP=$(curl -sf https://api.ipify.org || true)
  if [ -n "$IP" ]; then
    curl -sf "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=${IP}" || true
    echo "DuckDNS updated: ${DUCKDNS_SUBDOMAIN}.duckdns.org -> ${IP}"
  fi
fi

# Start FastAPI in background
uvicorn main:app --host 127.0.0.1 --port 8000 &

# Caddy handles HTTPS, listens on 443 and proxies to uvicorn
exec caddy run --config /app/Caddyfile --adapter caddyfile
