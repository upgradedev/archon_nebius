"""
Reference extractors for the evaluation harness.

An extractor maps a ground-truth case -> list[ExtractedDocument] (the real
extraction model). Two are provided here:

  * `perfect_extractor`  — returns exactly the fields the CURRENT production
    prompt emits (see `jobs/extraction/extractors/image.py::EXTRACTION_PROMPT`):
    generic document fields + `total_amount`, plus the payroll fields the prompt
    now requests (employer_cost_total / net_pay_total / gross_pay_total /
    employee_count on the register). This is the real product's ceiling — it is
    faithful to what the deployed pipeline can know.

  * `degraded_extractor` — a deliberately weak extractor (numeric noise on the
    totals incl. employer_cost_total, a structural net-line misread on the
    register, and a generic/UNKNOWN doc_type on some docs) used as a sensitivity
    check: it must score measurably below the ceiling, the real ClassifierAgent
    must recover the generic doc_types from the text, and R2 must catch the
    structural error the perfect extractor never makes.

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
        # Payroll fields the CURRENT prompt now emits (register + bank). Perfect
        # extraction returns them from the label verbatim; these are what R2/R4
        # and the P&L agent read (employer_cost_total drives the fusion figure).
        "employee_count": label.get("employee_count"),
        "gross_pay_total": label.get("gross_pay_total"),
        "employer_cost_total": label.get("employer_cost_total"),
        "net_pay_total": label.get("net_pay_total"),
        "employee_name": label.get("employee_name"),
        "employee_code": label.get("employee_code"),
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
        # numeric noise on ~half the totals -> field + fusion accuracy fall.
        # employer_cost_total (the register's fusion figure) is noised by the
        # same factor as total_amount, so fusion still collapses now that the
        # P&L agent reads the explicit field rather than total_amount.
        if rng.random() < 0.5 and d.get("total_amount"):
            factor = rng.uniform(0.94, 1.06)
            overrides["total_amount"] = round(d["total_amount"] * factor, 2)
            if d.get("employer_cost_total"):
                overrides["employer_cost_total"] = round(d["employer_cost_total"] * factor, 2)
        # STRUCTURAL extraction error on the register: the gross-pay line is
        # misread as the net-pay line. employer_cost/net collapses from ~1.73 to
        # ~1.26, which falls below R2's [1.40, 2.60] band -> R2 fires and flags
        # the corrupted extraction. This is the realistic failure R2 exists for
        # (numeric ±6% noise alone stays inside the band), so R2 earns its place.
        # It touches net_pay_total only, not employer_cost_total, so it does not
        # double-count against the fusion figure.
        if d["doc_type"] == "payroll_register" and d.get("gross_pay_total"):
            overrides["net_pay_total"] = d["gross_pay_total"]
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
