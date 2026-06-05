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
Analyse this document image — it may be in Greek or English.

Extract ALL of the following fields as JSON (use null for missing fields):
{
  "doc_type": "invoice|payroll|expense|sales|unknown",
  "detected_language": "ISO 639-1 code, e.g. el or en",
  "issue_date": "YYYY-MM-DD or null",
  "vendor_name": "string or null",
  "vendor_tax_id": "string (ΑΦΜ for Greek) or null",
  "recipient_name": "string or null",
  "currency": "ISO 4217 code, default EUR",
  "subtotal": number_or_null,
  "vat_amount": number_or_null,
  "vat_rate_pct": number_or_null,
  "total_amount": number (required),
  "line_items": [{"description": "...", "quantity": n, "unit_price": n, "total": n}],
  "payment_due_date": "YYYY-MM-DD or null",
  "invoice_number": "string or null",
  "notes": "string or null",
  "confidence": 0.0_to_1.0
}

Return ONLY the JSON object. No markdown, no explanation.
"""


class ImageExtractor(BaseExtractor):
    def __init__(self):
        self.client = OpenAI(
            base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
            api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
        )
        self.model = os.getenv("VISION_MODEL", "Qwen/Qwen2-VL-72B-Instruct")

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
        data = json.loads(raw.strip())

        return ExtractedDocument(
            source_file=path.name,
            doc_type=DocType(data.get("doc_type", "unknown")),
            detected_language=data.get("detected_language", "el"),
            issue_date=data.get("issue_date"),
            vendor_name=data.get("vendor_name"),
            vendor_tax_id=data.get("vendor_tax_id"),
            recipient_name=data.get("recipient_name"),
            currency=data.get("currency", "EUR"),
            subtotal=data.get("subtotal"),
            vat_amount=data.get("vat_amount"),
            vat_rate_pct=data.get("vat_rate_pct"),
            total_amount=float(data.get("total_amount", 0)),
            line_items=[LineItem(**li) for li in data.get("line_items", [])],
            payment_due_date=data.get("payment_due_date"),
            invoice_number=data.get("invoice_number"),
            notes=data.get("notes"),
            raw_text_excerpt="[image document]",
            extraction_model=self.model,
            confidence=float(data.get("confidence", 0.85)),
        )


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
