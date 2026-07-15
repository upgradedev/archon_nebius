# Native Endpoint HTTPS — retiring the Caddy + DuckDNS chain

**Status:** implemented on branch, **not yet cut over live**. Cut-over is gated on
the verification checklist below.

## What changed

Nebius Serverless AI Endpoints now expose each HTTP container port through a
platform-**managed HTTPS URL** (a trusted certificate, shown in
`status.public_endpoints`). That makes the entire hand-rolled TLS/DNS chain
unnecessary.

### Before (the fragile chain, source of the recurring 502s)

```
Firebase BFF  ──►  https://archon-api.duckdns.org   (verify=False)
                     │  DuckDNS A-record, repointed to the endpoint's public IP each deploy
                     ▼
              Endpoint  --public --container-port 443
                     └─ in-container Caddy (tls internal, self-signed) → uvicorn :8000
                     └─ Caddy cert store saved/restored via S3
```

Failure modes this produced: a NAT **egress-vs-ingress** DuckDNS mismatch (the
A-record pointed at an unreachable IP), a flaky public IP that dropped inbound
SYNs, and a self-signed cert that forced `verify=False` end to end.

### After

```
Firebase BFF  ──►  https://<id>.<region>.nebius.cloud   (verify=True)
                     ▼
              Endpoint  --container-port 8000   (no --public)
                     └─ uvicorn :8000 (plain HTTP; Nebius terminates TLS at the managed URL)
```

Deleted: `backend/Caddyfile`, `backend/start.sh`, `backend/Dockerfile.https`,
`.github/workflows/update-duckdns.yml`, the `DUCKDNS_*`/`CADDY_DOMAIN` env vars.
Added: `backend/Dockerfile.endpoint` (plain uvicorn on 8000, repo-root context so
it still carries `jobs/` for the inline runner). The deploy reads the managed URL
from `status.public_endpoints` and prints it; set it on the Firebase function as
`NEBIUS_BACKEND_URL` so the BFF forwards `/api/**` there.

## Why it's a net win

- Removes the single most incident-prone subsystem (DuckDNS repoint, self-signed
  cert, S3 cert store).
- Removes `verify=False` on both hops — a real TLS-verified path end to end.
- Fewer moving parts in the deploy and a smaller image (no Caddy, no curl).

## Pre-live verification checklist (do this before cutting over)

The public docs confirm the managed URL and that `--public` is *not required* to
reach the endpoint, but three facts must be measured on a throwaway endpoint
before the live cut-over — the live demo currently works, so we don't gamble it:

1. **Managed URL appears without `--public`.** Create with `--container-port 8000`,
   no `--public` → `status.public_endpoints[0]` is a `https://…` host (not `IP:port`).
2. **The ingress is open (unauthenticated).** `curl https://<managed>/health` returns
   200 with **no** Nebius IAM token. If the ingress enforces its own auth, the
   browser→BFF→URL hop needs a token injected — a different design; do not cut over.
3. **Stability across recreate.** Note the URL, recreate the endpoint, compare.
   - Stable → set `NEBIUS_BACKEND_URL` on the Firebase function once.
   - Not stable → the backend deploy must push the new URL to the function env on
     every deploy (the deploy already resolves + loudly reports it for this).

Also sanity-check cold-start latency through the managed URL against the Firebase
60s / axios 120s ceilings.

## Verified live (2026-07-15)

Merging the migration triggered `Deploy to Nebius`, which created the endpoint
with the new config. Measured on the live endpoint:

- Managed URL appeared **without `--public`**: `https://port8000-<rand>.tunnel.applications.eu-west1.nebius.cloud`.
- Ingress is **open/unauthenticated**: `curl /health` → `200` in ~0.25s, no IAM token.
- **NOT stable across recreate:** the `<rand>` token is per-endpoint (≠ the endpoint
  id), and blue/green uses a unique name per deploy → a fresh URL every deploy.

## The BFF coupling (why every deploy re-points the function)

Because the URL changes per deploy and the Firebase BFF holds it as
`NEBIUS_BACKEND_URL` (in `frontend/functions/.env`, gitignored), a backend deploy
that does **not** update the function leaves the live BFF pointing at the previous,
now-deleted endpoint (a 502). So `deploy-nebius.yml` re-points the function on every
deploy: it resolves the managed URL, writes `frontend/functions/.env`, and runs
`firebase deploy --only functions`, then curls `https://archon-pnl.web.app/api/health`
to confirm 200.

This is **guarded on the `FIREBASE_SERVICE_ACCOUNT` CI secret** — a GCP service-account
key JSON. Without it the step is a loud no-op (the deploy still succeeds and the job
summary prints the exact manual repoint command), so a missing secret can never
silently take the demo down. The service account needs roles to deploy a Gen2
function: `roles/firebase.admin`, `roles/cloudfunctions.admin`, `roles/run.admin`,
`roles/iam.serviceAccountUser`, `roles/artifactregistry.admin`, and
`roles/cloudbuild.builds.editor` (or, simplest, `roles/editor` + `roles/firebase.admin`).

## Rollback

The change is branch-isolated. If a live cut-over misbehaves, redeploy the
previous image tag (blue/green keeps the prior endpoint until the new one is
RUNNING) and restore `NEBIUS_BACKEND_URL` to the last-good target.
