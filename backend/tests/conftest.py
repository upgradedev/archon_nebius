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
