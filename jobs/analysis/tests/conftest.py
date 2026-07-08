"""
Shared fixtures for the analysis-endpoint unit/integration tests.

These tests exercise the REAL analysis agents (PnLAgent, CashFlowAgent,
EmployeeAgent, ValidatorAgent, ReconciliationAgent, ClassifierAgent, NarratorAgent)
and the /analyze orchestrator over the analysis-tier `ExtractedDoc` model — no
network: the LLM (narrator) and S3 (storage) are mocked.

The analysis pipeline ships its own top-level `models`/`agents` packages, so
this suite must run in its own process (separate `pytest` invocation) to avoid
colliding with the extraction pipeline's identically-named packages. See
`scripts/coverage.sh`.
"""
import os
import sys
from pathlib import Path

# Dummy inference creds so `agents.narrator` (imported eagerly by agents/__init__)
# constructs without a real key. No network is ever hit — the client is mocked.
os.environ.setdefault("NEBIUS_INFERENCE_BASE_URL", "http://localhost/v1")
os.environ.setdefault("NEBIUS_INFERENCE_API_KEY", "test-key")

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS_ROOT))

import pytest  # noqa: E402
from models.financial import ExtractedDoc  # noqa: E402


# Every `X | None` field on ExtractedDoc has NO default → it is REQUIRED
# (ADR-006). The factory supplies a complete, valid baseline so each test
# overrides only the fields under test.
_DEFAULTS = dict(
    source_file="doc.pdf",
    doc_type="invoice",
    detected_language="el",
    issue_date="2026-01-15",
    vendor_name="Acme EE",
    vendor_tax_id="EL123456789",
    recipient_name="My Company SA",
    currency="EUR",
    subtotal=None,
    vat_amount=None,
    vat_rate_pct=None,
    total_amount=100.0,
    payment_due_date=None,
    invoice_number="INV-1",
    notes=None,
    confidence=0.9,
)


def make_doc(**overrides) -> ExtractedDoc:
    data = {**_DEFAULTS, **overrides}
    return ExtractedDoc(**data)


@pytest.fixture
def doc():
    """Factory fixture: `doc(doc_type="payslip", total_amount=900)`."""
    return make_doc
