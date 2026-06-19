"""DOCX / DOC extractor — uses python-docx then delegates to text LLM."""

import os
import json
from pathlib import Path

from docx import Document
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseExtractor
from .image import EXTRACTION_PROMPT
from models.document import ExtractedDocument, DocType, LineItem


class DocxExtractor(BaseExtractor):
    def __init__(self):
        self.client = OpenAI(
            base_url=os.environ["NEBIUS_INFERENCE_BASE_URL"],
            api_key=os.environ["NEBIUS_INFERENCE_API_KEY"],
        )
        self.model = os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in {".docx", ".doc"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def extract(self, path: Path) -> ExtractedDocument:
        text = _extract_docx_text(path)

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
            raw_text_excerpt=text[:500],
            extraction_model=self.model,
            confidence=float(data.get("confidence", 0.88)),
        )


def _extract_docx_text(path: Path) -> str:
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    # Also extract table cell text
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())
    return "\n".join(paragraphs)
