"""
PDF extractor.

Strategy:
  1. Try pdfplumber for digital (text-layer) PDFs.
  2. If text yield is too low (scanned), convert pages to images
     and delegate to ImageExtractor.
"""

import os
import json
import tempfile
from pathlib import Path

import pdfplumber
import fitz  # PyMuPDF
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseExtractor
from .image import ImageExtractor, EXTRACTION_PROMPT
from models.document import ExtractedDocument, DocType, LineItem

MIN_TEXT_CHARS = 80   # below this → treat as scanned


class PdfExtractor(BaseExtractor):
    def __init__(self):
        self.image_extractor = ImageExtractor()
        self.client = OpenAI(
            base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
            api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
        )
        self.model = os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def extract(self, path: Path) -> ExtractedDocument:
        text = _extract_text(path)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return self._extract_from_text(path, text)
        # Scanned PDF — convert first page to image and use vision
        return self._extract_via_vision(path)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _extract_from_text(self, path: Path, text: str) -> ExtractedDocument:
        prompt = (
            "You are a financial document extraction specialist.\n"
            "Extract from the following document text (may be Greek or English).\n\n"
            f"DOCUMENT TEXT:\n{text[:4000]}\n\n"
            + EXTRACTION_PROMPT
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        from .image import _clean_json, _safe_doc_type
        data = json.loads(_clean_json(raw))
        return ExtractedDocument(
            source_file=path.name,
            doc_type=_safe_doc_type(data.get("doc_type")),
            detected_language=data.get("detected_language") or "el",
            issue_date=data.get("issue_date") or None,
            vendor_name=data.get("vendor_name") or None,
            vendor_tax_id=data.get("vendor_tax_id") or None,
            recipient_name=data.get("recipient_name") or None,
            currency=data.get("currency") or "EUR",
            subtotal=_safe_float(data.get("subtotal")),
            vat_amount=_safe_float(data.get("vat_amount")),
            vat_rate_pct=_safe_float(data.get("vat_rate_pct")),
            total_amount=_safe_float(data.get("total_amount")) or 0.0,
            line_items=_safe_line_items(data.get("line_items")),
            payment_due_date=data.get("payment_due_date") or None,
            invoice_number=data.get("invoice_number") or None,
            notes=data.get("notes") or None,
            raw_text_excerpt=text[:500],
            extraction_model=self.model,
            confidence=float(data.get("confidence") or 0.9),
        )

    def _extract_via_vision(self, path: Path) -> ExtractedDocument:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            doc = fitz.open(str(path))
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            pix.save(str(tmp_path))
            result = self.image_extractor.extract(tmp_path)
            result.source_file = path.name
            return result
        finally:
            tmp_path.unlink(missing_ok=True)


def _extract_text(path: Path) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:5]:  # first 5 pages is enough for invoice extraction
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)
