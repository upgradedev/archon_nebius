"""
Vision extractor — handles JPG, PNG, TIFF, WEBP, and scanned PDF pages.

Uses Qwen2-VL via the Nebius Inference API (OpenAI-compatible).
The model reads Greek natively; no translation step is needed.
"""

import base64
import os
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from PIL import Image
import io

from .base import BaseExtractor
from models.document import ExtractedDocument, DocType, LineItem

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}

EXTRACTION_PROMPT = """You are a financial document extraction specialist.
Analyse this document — it may be in Greek or English.

Extract ALL of the following fields as a JSON object (use null for missing fields).
Choose doc_type from EXACTLY one of these values:
  invoice, sales, expense, payroll_register, bank_confirmation, payslip, payroll, account_statement, unknown

{
  "doc_type": "one of the values listed above",
  "detected_language": "ISO 639-1 code, e.g. el or en",
  "issue_date": "YYYY-MM-DD or null",
  "vendor_name": "string or null",
  "vendor_tax_id": "string or null",
  "recipient_name": "string or null",
  "currency": "EUR",
  "subtotal": null,
  "vat_amount": null,
  "vat_rate_pct": null,
  "total_amount": 0.0,
  "line_items": [],
  "payment_due_date": "YYYY-MM-DD or null",
  "invoice_number": "string or null",
  "notes": "string or null",
  "confidence": 0.9
}

IMPORTANT: Return ONLY the raw JSON object. No markdown fences, no extra text.
"""


class ImageExtractor(BaseExtractor):
    def __init__(self):
        self.client = OpenAI(
            base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
            api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
        )
        self.model = os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in IMAGE_EXTENSIONS

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def extract(self, path: Path) -> ExtractedDocument:
        img_b64 = _encode_image(path)
        import json

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
            max_tokens=2048,
            temperature=0.1,
        )

        raw = response.choices[0].message.content or "{}"
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
            raw_text_excerpt="[image document]",
            extraction_model=self.model,
            confidence=float(data.get("confidence") or 0.85),
        )


def _clean_json(raw: str) -> str:
    """Strip markdown code fences and surrounding whitespace."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]  # drop opening fence line
        raw = raw.rsplit("```", 1)[0]  # drop closing fence
    return raw.strip()


def _safe_doc_type(value: str | None) -> DocType:
    try:
        return DocType(value) if value else DocType.UNKNOWN
    except ValueError:
        return DocType.UNKNOWN


def _safe_float(value) -> float | None:
    """Return float or None — never raise on null/empty/non-numeric LLM output."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_line_items(value) -> list:
    """Return list of LineItem dicts — never raise on null LLM output."""
    if not value or not isinstance(value, list):
        return []
    items = []
    for li in value:
        if isinstance(li, dict) and "description" in li and "total" in li:
            try:
                items.append(LineItem(**li))
            except Exception:
                pass
    return items


def _encode_image(path: Path) -> str:
    """Resize image to max 1600px on longest side, encode as JPEG base64."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        max_side = 1600
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
