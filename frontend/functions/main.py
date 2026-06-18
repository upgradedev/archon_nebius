"""
Firebase Cloud Function (Gen 2) — BFF proxy for the Archon backend.

Forwards /api/** from Firebase Hosting to the Nebius backend so that TLS
termination lives at Firebase (Google-managed cert, no Let's Encrypt rate
limits). The Nebius container's Caddy TLS cert is only used for the
server-to-server hop, which is not browser-visible.
"""

import json
import os

import httpx
from firebase_functions import https_fn

BACKEND_URL = os.environ.get(
    "NEBIUS_BACKEND_URL", "https://archon-api.duckdns.org"
).rstrip("/")

_DROP_REQ_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
})
_DROP_RESP_HEADERS = frozenset({
    "content-encoding", "transfer-encoding", "connection", "keep-alive",
})


@https_fn.on_request(timeout_sec=120, memory=256, region="us-central1")
def archon_proxy(req: https_fn.Request) -> https_fn.Response:
    path = req.full_path if req.query_string else req.path
    url = f"{BACKEND_URL}{path}"

    fwd_headers = {
        k: v for k, v in req.headers.items()
        if k.lower() not in _DROP_REQ_HEADERS
    }

    try:
        resp = httpx.request(
            method=req.method,
            url=url,
            headers=fwd_headers,
            content=req.get_data(),
            verify=False,   # server-to-server: staging cert is fine
            timeout=120.0,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
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

    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _DROP_RESP_HEADERS
    }
    return https_fn.Response(
        response=resp.content,
        status=resp.status_code,
        headers=resp_headers,
    )
