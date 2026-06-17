"""
Firebase ID token verification.

Verifies tokens issued by Firebase Authentication (Google Sign-In).
Public keys are fetched from Google's JWKS endpoint and cached for their
Cache-Control max-age (typically 6 hours). No service account required.
"""

import os
import threading
import time

import httpx
import jwt
from cryptography import x509
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "archon-pnl")
_KEYS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)

_lock = threading.Lock()
_cache: dict[str, str] = {}
_cache_until: float = 0.0


def _public_keys() -> dict[str, str]:
    global _cache, _cache_until
    with _lock:
        if time.monotonic() < _cache_until and _cache:
            return _cache
        resp = httpx.get(_KEYS_URL, timeout=10)
        resp.raise_for_status()
        max_age = 3600
        for part in resp.headers.get("Cache-Control", "").split(","):
            part = part.strip()
            if part.startswith("max-age="):
                try:
                    max_age = int(part[8:])
                except ValueError:
                    pass
        _cache = resp.json()
        _cache_until = time.monotonic() + max_age
        return _cache


_bearer = HTTPBearer(auto_error=False)


def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        keys = _public_keys()
        if kid not in keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unknown signing key",
            )
        cert = x509.load_pem_x509_certificate(keys[kid].encode())
        payload = jwt.decode(
            token,
            cert.public_key(),
            algorithms=["RS256"],
            audience=FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )
