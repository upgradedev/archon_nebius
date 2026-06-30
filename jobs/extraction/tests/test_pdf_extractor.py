"""
PdfExtractor — digital (text-layer) PDFs go through the text LLM; scanned PDFs
(low text yield) fall back to the vision ImageExtractor. Both LLM calls mocked.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import fitz  # PyMuPDF

from extractors.pdf import PdfExtractor, _extract_text, MIN_TEXT_CHARS
from models.document import DocType


def _text_pdf(path: Path, body: str):
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 72), body)
    d.save(str(path))
    d.close()


def _blank_pdf(path: Path):
    d = fitz.open()
    d.new_page()   # no text → scanned-like
    d.save(str(path))
    d.close()


def _fake_client(content):
    resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: resp)))


def test_can_handle():
    ex = PdfExtractor()
    assert ex.can_handle(Path("x.pdf")) is True
    assert ex.can_handle(Path("x.png")) is False


def test_extract_text_reads_digital_pdf(tmp_path):
    p = tmp_path / "digital.pdf"
    _text_pdf(p, "This is a digital invoice with a clear, selectable text layer and plenty of characters in it.")
    text = _extract_text(p)
    assert "digital invoice" in text
    assert len(text) >= MIN_TEXT_CHARS


def test_extract_routes_to_text_llm(tmp_path):
    p = tmp_path / "digital.pdf"
    _text_pdf(p, "Invoice number 42 total amount one thousand euros, vendor Acme, plenty of text here.")
    ex = PdfExtractor()
    ex.client = _fake_client(json.dumps({
        "doc_type": "invoice", "detected_language": "en",
        "total_amount": 1000, "invoice_number": "42",
        "subtotal": None, "vat_amount": None,
    }))
    result = ex.extract(p)
    assert result.doc_type == DocType.INVOICE
    assert result.total_amount == 1000.0
    assert result.invoice_number == "42"
    assert result.source_file == "digital.pdf"


def test_extract_text_llm_handles_null_fields(tmp_path):
    p = tmp_path / "digital.pdf"
    _text_pdf(p, "Some Greek-ish invoice text long enough to exceed the threshold for OCR fallback.")
    ex = PdfExtractor()
    # null/garbage numerics must not crash (ADR-003 via image helpers)
    ex.client = _fake_client(json.dumps({
        "doc_type": "expense", "total_amount": None,
        "subtotal": "x", "confidence": None,
    }))
    result = ex.extract(p)
    assert result.total_amount == 0.0     # null → 0.0
    assert result.subtotal is None        # garbage → None
    assert result.confidence == 0.9       # null → default


def test_extract_falls_back_to_vision_for_scanned(tmp_path):
    p = tmp_path / "scanned.pdf"
    _blank_pdf(p)
    ex = PdfExtractor()

    # the vision path delegates to ImageExtractor.extract — mock it
    from conftest import make_doc
    sentinel = make_doc(source_file="placeholder", doc_type=DocType.PAYSLIP, total_amount=900)
    ex.image_extractor.extract = lambda tmp: sentinel

    result = ex.extract(p)
    assert result.doc_type == DocType.PAYSLIP
    assert result.total_amount == 900.0
    # source_file is rewritten to the real pdf name
    assert result.source_file == "scanned.pdf"
