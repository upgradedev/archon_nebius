"""
Shared fixtures for backend unit tests.
Sets SKIP_AUTH=true and JOB_RUNNER_BACKEND=local before importing the app
so no Firebase token or Nebius CLI is required.
"""
import os
import sys

# These must be set before `from main import app` — auth.py and nebius.py
# read them at module load time.
os.environ.setdefault("SKIP_AUTH", "true")
os.environ.setdefault("JOB_RUNNER_BACKEND", "local")
os.environ.setdefault("EXTRACTION_SERVICE_URL", "http://extraction:8002")
os.environ.setdefault("ANALYSIS_SERVICE_URL", "http://analysis:8001")
os.environ.setdefault("NEBIUS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("STORAGE_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("NEBIUS_REGION", "us-east-1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

# Ensure backend package root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    from main import app as _app
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def safe_client(app):
    """SKIP_AUTH client that returns 5xx as a status code instead of raising.

    Required by the abuse/DoS-lite pen-tests: with the default TestClient
    (``raise_server_exceptions=True``) a server-side 500 raises INTO the test, so
    you cannot assert "malformed input -> 4xx, never 5xx". This client makes that
    assertion possible.
    """
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_client(app):
    """A TestClient with Firebase verification ACTIVE (SKIP_AUTH off).

    Used by the pen-test suite to exercise the real auth boundary (missing /
    bogus token -> 401) and to prove server errors surface as clean status codes
    (``raise_server_exceptions=False``) rather than raising into the test.

    Guaranteed teardown restores ``auth._SKIP_AUTH = True`` so a leaked ``False``
    can never 401 every subsequent backend test in the same process — mirrors the
    try/finally discipline in test_auth.py.
    """
    import auth as auth_module

    original = auth_module._SKIP_AUTH
    auth_module._SKIP_AUTH = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        auth_module._SKIP_AUTH = original
