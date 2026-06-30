"""
Shared fixtures for the extraction-job unit tests.

Exercises the REAL extraction agents (ClassifierAgent, EventLinkerAgent,
ValidatorAgent) and the extractors (LLM mocked) over the extraction-tier
`ExtractedDocument` model. Runs in its own process (separate pytest invocation)
because the extraction pipeline ships top-level `models`/`agents`/`extractors`
packages that collide with the analysis pipeline's. See `scripts/coverage.sh`.
"""
import os
import sys
from pathlib import Path

# Extractors construct an OpenAI client from these in __init__; no network is hit
# (the client/method is mocked in each test).
os.environ.setdefault("NEBIUS_INFERENCE_BASE_URL", "http://localhost/v1")
os.environ.setdefault("NEBIUS_INFERENCE_API_KEY", "test-key")

EXTRACTION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXTRACTION_ROOT))

import pytest  # noqa: E402
from models.document import ExtractedDocument, DocType  # noqa: E402


# Every `X | None` field without a default is REQUIRED (ADR-006); supply a full
# valid baseline so tests override only what they assert on.
_DEFAULTS = dict(
    source_file="doc.pdf",
    doc_type=DocType.UNKNOWN,
    detected_language="el",
    issue_date="2026-01-15",
    vendor_name=None,
    vendor_tax_id=None,
    recipient_name="My Company SA",
    currency="EUR",
    subtotal=None,
    vat_amount=None,
    vat_rate_pct=None,
    total_amount=0.0,
    line_items=[],
    payment_due_date=None,
    invoice_number=None,
    notes=None,
    raw_text_excerpt="",
    extraction_model="test",
    confidence=0.9,
)


def make_doc(**overrides) -> ExtractedDocument:
    return ExtractedDocument(**{**_DEFAULTS, **overrides})


@pytest.fixture
def doc():
    return make_doc
