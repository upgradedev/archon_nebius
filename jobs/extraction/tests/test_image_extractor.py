"""
ImageExtractor + the pure JSON/number helpers that enforce ADR-003 null-safety.
No network: the OpenAI client is replaced after construction.
"""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from extractors import image
from extractors.image import (
    ImageExtractor, _clean_json, _safe_doc_type, _safe_float, _safe_int,
    _safe_line_items, _encode_image,
)
from models.document import DocType


# ── _clean_json ───────────────────────────────────────────────────────────────

def test_clean_json_strips_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert json.loads(_clean_json(raw)) == {"a": 1}


def test_clean_json_plain_passthrough():
    assert _clean_json('  {"a": 1}  ') == '{"a": 1}'


# ── _safe_doc_type (ADR-003) ──────────────────────────────────────────────────

def test_safe_doc_type_valid():
    assert _safe_doc_type("payslip") == DocType.PAYSLIP


def test_safe_doc_type_none_and_invalid_default_unknown():
    assert _safe_doc_type(None) == DocType.UNKNOWN
    assert _safe_doc_type("not-a-type") == DocType.UNKNOWN


# ── _safe_float (ADR-003: never raise on null/empty/garbage) ──────────────────

@pytest.mark.parametrize("value,expected", [
    (None, None), ("", None), ("abc", None),
    ("12.5", 12.5), (3, 3.0), (0, 0.0),
])
def test_safe_float(value, expected):
    assert _safe_float(value) == expected


# ── _safe_int (ADR-003: payroll employee_count, never raise) ──────────────────

@pytest.mark.parametrize("value,expected", [
    (None, None), ("", None), ("abc", None),
    ("4", 4), (5, 5), ("3.0", 3), (2.9, 2),
])
def test_safe_int(value, expected):
    assert _safe_int(value) == expected


# ── _safe_line_items (ADR-003) ────────────────────────────────────────────────

def test_safe_line_items_none_and_non_list():
    assert _safe_line_items(None) == []
    assert _safe_line_items("nope") == []


def test_safe_line_items_keeps_valid_drops_invalid():
    items = _safe_line_items([
        {"description": "Widget", "total": 10.0},   # valid
        {"description": "missing total"},            # dropped (no total)
        {"total": 5.0},                              # dropped (no description)
        "garbage",                                   # dropped (not dict)
    ])
    assert len(items) == 1
    assert items[0].description == "Widget"


# ── _encode_image ─────────────────────────────────────────────────────────────

def test_encode_image_resizes_and_returns_base64(tmp_path):
    p = tmp_path / "big.png"
    Image.new("RGB", (3200, 100), "white").save(p)
    b64 = _encode_image(p)
    assert isinstance(b64, str) and len(b64) > 0
    # decodes back to a JPEG capped at 1600px on the long side
    from base64 import b64decode
    out = Image.open(io.BytesIO(b64decode(b64)))
    assert max(out.size) == 1600


# ── ImageExtractor ────────────────────────────────────────────────────────────

def test_can_handle_extensions():
    ex = ImageExtractor()
    assert ex.can_handle(Path("x.png")) is True
    assert ex.can_handle(Path("x.JPG")) is True
    assert ex.can_handle(Path("x.pdf")) is False


def _fake_client(content: str):
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    resp = SimpleNamespace(choices=[choice])
    create = lambda **kwargs: resp  # noqa: E731
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_extract_parses_llm_json_with_nulls(tmp_path):
    img = tmp_path / "inv.png"
    Image.new("RGB", (50, 50), "white").save(img)

    ex = ImageExtractor()
    # LLM returns nulls in numeric fields and a malformed line item — must not raise
    ex.client = _fake_client(json.dumps({
        "doc_type": "invoice",
        "detected_language": "el",
        "total_amount": "1234.50",
        "subtotal": None,
        "vat_amount": "abc",
        "vendor_name": "Acme",
        "line_items": [{"description": "x"}],
        "confidence": None,
    }))

    result = ex.extract(img)
    assert result.doc_type == DocType.INVOICE
    assert result.total_amount == 1234.50
    assert result.subtotal is None
    assert result.vat_amount is None          # "abc" → None, not a crash
    assert result.line_items == []            # malformed item dropped
    assert result.confidence == 0.85          # null → default
    assert result.source_file == "inv.png"


def test_extract_empty_content_defaults_unknown(tmp_path):
    img = tmp_path / "blank.png"
    Image.new("RGB", (40, 40), "white").save(img)
    ex = ImageExtractor()
    ex.client = _fake_client("")   # → "{}" fallback in extract()
    result = ex.extract(img)
    assert result.doc_type == DocType.UNKNOWN
    assert result.total_amount == 0.0


def test_extract_maps_payroll_register_fields(tmp_path):
    # A payroll_register read populates the fields R2/R4 and the P&L agent need.
    img = tmp_path / "register.png"
    Image.new("RGB", (60, 60), "white").save(img)
    ex = ImageExtractor()
    ex.client = _fake_client(json.dumps({
        "doc_type": "payroll_register",
        "detected_language": "en",
        "total_amount": "17300.00",
        "gross_pay_total": "13730.00",
        "employer_cost_total": "17300.00",
        "net_pay_total": "10000.00",
        "employee_count": "4",
    }))
    result = ex.extract(img)
    assert result.doc_type == DocType.PAYROLL_REGISTER
    assert result.employer_cost_total == 17300.0
    assert result.net_pay_total == 10000.0
    assert result.gross_pay_total == 13730.0
    assert result.employee_count == 4
