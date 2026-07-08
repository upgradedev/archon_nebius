"""
Firebase Cloud Function (Gen 2) — BFF proxy for the Archon backend.

Forwards /api/** from Firebase Hosting to the Nebius backend so that TLS
termination lives at Firebase (Google-managed cert, no Let's Encrypt rate
limits). The Nebius container's Caddy TLS cert is only used for the
server-to-server hop, which is not browser-visible.

Reliability note: the Nebius endpoint is reached over its raw public IP
(via archon-api.duckdns.org). That IP intermittently drops inbound TCP SYN
packets, so a single connect attempt can hang ~20s and then fail with a
connect error even though the backend app itself is healthy (a direct curl
returns 200 /health and 401 on a protected route). A single failed attempt
surfaced to the browser as an HTTP 502. We therefore retry connect-layer
failures on a fresh connection with a short connect timeout: a flaky attempt
is cheap to abandon and a healthy attempt wins well within the function's
120s budget.
"""

import json
import os
import time

import httpx
from firebase_functions import https_fn

BACKEND_URL = os.environ.get(
    "NEBIUS_BACKEND_URL", "https://archon-api.duckdns.org"
).rstrip("/")

# Short connect timeout so a dropped-SYN attempt is abandoned quickly; generous
# read/write so real upload + analysis work can finish. More short attempts are
# better than fewer long attempts for the Nebius public-IP flake observed here.
_TIMEOUT = httpx.Timeout(connect=4.0, read=115.0, write=115.0, pool=4.0)
_CONNECT_ATTEMPTS = 8

# Transport failures where the request never produced a response. Safe to retry
# even for non-idempotent POSTs because nothing was delivered to the backend.
_RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)

_DROP_REQ_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
})
_DROP_RESP_HEADERS = frozenset({
    "content-encoding", "transfer-encoding", "connection", "keep-alive",
})

# Paths the BFF forwards WITHOUT a bearer token. /api/health is the cold-start
# liveness probe (#115): the frontend polls it unauthenticated to detect when the
# Nebius endpoint has finished cold-starting. It MUST reach the backend (which
# serves /api/health unauthenticated by design) and return the backend's real
# status — while the endpoint is cold the forwarded request surfaces as 502/503,
# and it returns 200 the moment the backend is warm. The BFF must NOT synthesize
# its own 200 here: a synthesized 200 would falsely report "warm" while the
# endpoint is still cold, defeating the probe. Every other /api/** route still
# requires a bearer token below.
_PUBLIC_PATHS = frozenset({"/api/health"})


def _is_public(method: str, path: str) -> bool:
    """A request that the BFF forwards without requiring an Authorization header.

    Tight by design: exact normalized path match + GET only, so it can never
    open a write route or a sibling path.
    """
    return method.upper() == "GET" and path.rstrip("/") in _PUBLIC_PATHS


@https_fn.on_request(timeout_sec=120, memory=256, region="us-central1")
def archon_proxy(req: https_fn.Request) -> https_fn.Response:
    if not req.headers.get("authorization") and not _is_public(req.method, req.path):
        return https_fn.Response(
            response=json.dumps({"detail": "Missing bearer token"}),
            status=401,
            headers={"Content-Type": "application/json"},
        )

    path = req.full_path if req.query_string else req.path
    url = f"{BACKEND_URL}{path}"

    fwd_headers = {
        k: v for k, v in req.headers.items()
        if k.lower() not in _DROP_REQ_HEADERS
    }
    body = req.get_data()

    resp = None
    last_exc: Exception | None = None
    for attempt in range(_CONNECT_ATTEMPTS):
        try:
            resp = httpx.request(
                method=req.method,
                url=url,
                headers=fwd_headers,
                content=body,
                verify=False,   # server-to-server: staging cert is fine
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
            break
        except _RETRYABLE as exc:
            # Transient reachability failure (flaky public IP). Retry on a
            # fresh connection; only give up after the last attempt.
            last_exc = exc
            if attempt < _CONNECT_ATTEMPTS - 1:
                time.sleep(0.25 * (attempt + 1))
                continue
        except httpx.TimeoutException:
            # A genuine read/write timeout — the backend accepted the
            # connection but is taking too long. Don't hammer it.
            return https_fn.Response(
                response=json.dumps({"error": "backend timeout"}),
                status=504,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as exc:
            return https_fn.Response(
                response=json.dumps({"error": f"backend unreachable: {exc}"}),
                status=502,
                headers={"Content-Type": "application/json"},
            )

    if resp is None:
        return https_fn.Response(
            response=json.dumps({"error": f"backend unreachable: {last_exc}"}),
            status=502,
            headers={"Content-Type": "application/json"},
        )

    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _DROP_RESP_HEADERS
    }
    return https_fn.Response(
        response=resp.content,
        status=resp.status_code,
        headers=resp_headers,
    )
