#!/bin/sh
set -e

CADDY_DATA_DIR=/root/.local/share/caddy
S3_CERT_PREFIX=caddy-certs

# Restore Caddy cert store from S3 so redeployments reuse the existing cert
# and don't burn Let's Encrypt rate limits.
if [ -n "$NEBIUS_BUCKET_NAME" ] && [ -n "$AWS_ACCESS_KEY_ID" ]; then
  echo "Restoring Caddy cert store from S3..."
  python3 - <<'PYEOF'
import boto3, os, pathlib

bucket = os.environ["NEBIUS_BUCKET_NAME"]
endpoint = os.environ.get("STORAGE_ENDPOINT_URL", "https://storage.eu-west1.nebius.cloud")
prefix = "caddy-certs/"
local = pathlib.Path("/root/.local/share/caddy")

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)
try:
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix):]
            if not rel:
                continue
            dest = local / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(dest))
    print("Caddy cert store restored from S3.")
except Exception as e:
    print(f"Could not restore certs from S3 (first deploy is normal): {e}")
PYEOF
fi

# Update DuckDNS record to this container's public IP on startup
if [ -n "$DUCKDNS_TOKEN" ] && [ -n "$DUCKDNS_SUBDOMAIN" ]; then
  IP=$(curl -sf https://api.ipify.org || true)
  if [ -n "$IP" ]; then
    curl -sf "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=${IP}" || true
    echo "DuckDNS updated: ${DUCKDNS_SUBDOMAIN}.duckdns.org -> ${IP}"
  fi
fi

# On exit, upload the cert store back to S3
_upload_certs() {
  if [ -n "$NEBIUS_BUCKET_NAME" ] && [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo "Uploading Caddy cert store to S3..."
    python3 - <<'PYEOF'
import boto3, os, pathlib

bucket = os.environ["NEBIUS_BUCKET_NAME"]
endpoint = os.environ.get("STORAGE_ENDPOINT_URL", "https://storage.eu-west1.nebius.cloud")
prefix = "caddy-certs/"
local = pathlib.Path("/root/.local/share/caddy")

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)
try:
    count = 0
    for f in local.rglob("*"):
        if f.is_file():
            key = prefix + str(f.relative_to(local))
            s3.upload_file(str(f), bucket, key)
            count += 1
    print(f"Uploaded {count} cert files to S3.")
except Exception as e:
    print(f"Could not upload certs to S3: {e}")
PYEOF
  fi
}
trap _upload_certs EXIT

# Start FastAPI in background
uvicorn main:app --host 127.0.0.1 --port 8000 &

# Caddy handles HTTPS, listens on 443 and proxies to uvicorn
exec caddy run --config /app/Caddyfile --adapter caddyfile
