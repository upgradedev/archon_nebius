"""
Firebase Cloud Function — BFF proxy for the Archon backend.

Forwards /api/** from Firebase Hosting to the Nebius backend so that TLS
termination lives at Firebase (Google-managed cert, no Let's Encrypt rate
limits). The Nebius container's Caddy TLS cert is only used for the
server-to-server hop, which is not browser-visible.
"""

import os
import functions_framework
import httpx

BACKEND_URL = os.environ.get(
    "NEBIUS_BACKEND_URL", "https://archon-api.duckdns.org"
).rstrip("/")

_DROP_REQ_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
})
_DROP_RESP_HEADERS = frozenset({
    "content-encoding", "transfer-encoding", "connection", "keep-alive",
})


@functions_framework.http
def archon_proxy(request):
    path = request.full_path if request.query_string else request.path
    url = f"{BACKEND_URL}{path}"

    fwd_headers = {
        k: v for k, v in request.headers
        if k.lower() not in _DROP_REQ_HEADERS
    }

    try:
        resp = httpx.request(
            method=request.method,
            url=url,
            headers=fwd_headers,
            content=request.get_data(),
            verify=False,   # server-to-server: staging cert is fine
            timeout=120.0,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        return {"error": "backend timeout"}, 504
    except httpx.RequestError as exc:
        return {"error": f"backend unreachable: {exc}"}, 502

    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _DROP_RESP_HEADERS
    }
    return resp.content, resp.status_code, resp_headers
