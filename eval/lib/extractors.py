"""
Reference extractors for the evaluation harness.

An extractor maps a ground-truth case -> list[ExtractedDocument] (the real
extraction model). Two are provided here:

  * `perfect_extractor`  — returns exactly the fields the CURRENT production
    prompt emits (see `jobs/extraction/extractors/image.py::EXTRACTION_PROMPT`):
    generic document fields + `total_amount`, and NOTHING payroll-specific
    (no employer_cost_total / net_pay_total / employee_count). This is the real
    product's ceiling — it is faithful to what the deployed pipeline can know.

  * `degraded_extractor` — a deliberately weak extractor (numeric noise, a
    dropped field, and a generic/UNKNOWN doc_type on some docs) used as a
    sensitivity check: it must score measurably below the ceiling, and the real
    ClassifierAgent must recover the generic doc_types from the text.

The live multimodal extractor (Qwen2.5-VL on Nebius) is the open slot — see
`eval/LIVE_EXTRACTION.md`.
"""

from __future__ import annotations

import random
import zlib


def _build(ExtractedDocument, DocType, label: dict, **overrides):
    """Construct an ExtractedDocument from a label dict (current-prompt fields)."""
    data = {
        "source_file": label["source_file"],
        "doc_type": DocType(label["doc_type"]),
        "detected_language": label.get("detected_language", "el"),
        "issue_date": label.get("issue_date"),
        "vendor_name": label.get("vendor_name"),
        "vendor_tax_id": label.get("vendor_tax_id"),
        "recipient_name": label.get("recipient_name"),
        "currency": label.get("currency", "EUR"),
        "subtotal": label.get("subtotal"),
        "vat_amount": label.get("vat_amount"),
        "vat_rate_pct": label.get("vat_rate_pct"),
        "total_amount": label.get("total_amount", 0.0),
        "line_items": [],
        "payment_due_date": label.get("payment_due_date"),
        "invoice_number": label.get("invoice_number"),
        "notes": label.get("notes"),
        "raw_text_excerpt": label.get("raw_text_excerpt", ""),
        "extraction_model": "harness:reference",
        "confidence": label.get("confidence", 0.95),
        # payslip identity fields ARE within the model (used by analytics);
        # the current prompt does not emit them, so perfect leaves them None
        # too, but we keep employee_code/name available for the wired variant.
    }
    data.update(overrides)
    return ExtractedDocument(**data)


def perfect_extractor(ext: dict, case: dict):
    """Ceiling: perfect read of the fields the current prompt actually emits."""
    ExtractedDocument = ext["models.document"].ExtractedDocument
    DocType = ext["models.document"].DocType
    return [_build(ExtractedDocument, DocType, d) for d in case["documents"]]


def degraded_extractor(ext: dict, case: dict, seed: int = 13):
    """
    Weak extractor: ~6% numeric noise on totals, one dropped total, and a
    generic 'payroll' doc_type for half the payroll docs (the ClassifierAgent
    is expected to recover these from the notes/raw-text keywords).
    """
    ExtractedDocument = ext["models.document"].ExtractedDocument
    DocType = ext["models.document"].DocType
    # stable per-case seed (hash() is salted per-process -> not reproducible)
    rng = random.Random(seed + zlib.crc32(case["case_id"].encode()))
    docs = []
    for i, d in enumerate(case["documents"]):
        overrides = {}
        # numeric noise on ~half the totals -> field + fusion accuracy fall
        if rng.random() < 0.5 and d.get("total_amount"):
            overrides["total_amount"] = round(d["total_amount"] * rng.uniform(0.94, 1.06), 2)
        # misclassify even-indexed payroll docs as the generic 'payroll' type.
        # Half keep their keyword text (the ClassifierAgent recovers them);
        # half are stripped of text (unrecoverable -> a real classification miss).
        if d["doc_type"] in ("payroll_register", "bank_confirmation", "payslip") and i % 2 == 0:
            overrides["doc_type"] = DocType.PAYROLL
            if rng.random() < 0.5:
                overrides["notes"] = None
                overrides["raw_text_excerpt"] = ""
        docs.append(_build(ExtractedDocument, DocType, d, **overrides))
    return docs
