"""
Offline orchestration test for the extraction-job entrypoint (jobs/extraction/
main.py) — the 4-agent wiring Extractor -> Classifier -> EventLinker -> Validator.

No network, no Docker, no LLM: the S3 boundary and the per-file extraction (the
only pieces that touch boto3 / the vision model) are mocked exactly as
test_pdf_extractor.py mocks the LLM client, so the REAL classifier, event-linker
and validator agents run and the three output artifacts (documents/events/
validation JSON) are asserted. This covers main.py in the offline gate — it was
previously omitted from .coveragerc and only exercised by the billable live E2E.
"""
import os
from pathlib import Path

# main.py reads these at import time (module-level os.environ[...]); set before import.
os.environ.setdefault("UPLOAD_ID", "up-test")
os.environ.setdefault("PERIOD", "2026-01")
os.environ.setdefault("NEBIUS_BUCKET_NAME", "archon-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("STORAGE_ENDPOINT_URL", "http://localhost:4566")

import main  # noqa: E402
from conftest import make_doc  # noqa: E402
from models.document import DocType  # noqa: E402


# ── full pipeline wiring ──────────────────────────────────────────────────────

def test_main_runs_full_agent_pipeline(monkeypatch):
    keys = [
        "raw-docs/2026-01/up-test/bank.pdf",
        "raw-docs/2026-01/up-test/register.pdf",
        "raw-docs/2026-01/up-test/s1.pdf",
        "raw-docs/2026-01/up-test/s2.pdf",
    ]
    monkeypatch.setattr(main, "_list_raw_files", lambda upload_id, period: keys)

    def fake_extract(key):
        name = key.split("/")[-1]
        if "bank" in name:
            return make_doc(source_file=name, doc_type=DocType.BANK_CONFIRMATION,
                            total_amount=10_000, issue_date="2026-01-28").model_dump()
        if "register" in name:
            return make_doc(source_file=name, doc_type=DocType.PAYROLL_REGISTER,
                            employer_cost_total=12_800, net_pay_total=10_000,
                            employee_count=2).model_dump()
        return make_doc(source_file=name, doc_type=DocType.PAYSLIP,
                        total_amount=5_000).model_dump()
    monkeypatch.setattr(main, "_extract_file", fake_extract)

    puts: dict[str, object] = {}
    monkeypatch.setattr(main, "_put_json", lambda key, data: puts.__setitem__(key, data))

    main.main()

    base = "extracted/2026-01/up-test"
    assert set(puts) == {f"{base}/documents.json", f"{base}/events.json", f"{base}/validation.json"}

    # All four documents survived deserialisation and classification.
    docs = puts[f"{base}/documents.json"]["documents"]
    assert len(docs) == 4

    # EventLinker fused the four payroll docs (same company + period) into ONE
    # complete event linking bank + register + 2 payslips.
    events = puts[f"{base}/events.json"]["events"]
    assert len(events) == 1
    ev = events[0]
    assert ev["is_complete"] is True
    assert ev["bank_confirmation"] is not None
    assert ev["payroll_register"] is not None
    assert len(ev["payslips"]) == 2

    # Validator produced R1-R4 and all pass on this internally-consistent event.
    summary = puts[f"{base}/validation.json"]["summary"]
    assert summary["total"] == 4
    assert summary["errors"] == 0
    assert summary["passed"] == 4


def test_main_deserialises_and_skips_malformed(monkeypatch):
    # One good doc + one structurally-broken extraction result (missing required
    # fields) — the broken one is skipped, the pipeline still completes.
    monkeypatch.setattr(main, "_list_raw_files", lambda upload_id, period: ["raw-docs/2026-01/up-test/a.pdf",
                                                                            "raw-docs/2026-01/up-test/b.pdf"])

    def fake_extract(key):
        if key.endswith("a.pdf"):
            return make_doc(source_file="a.pdf", doc_type=DocType.INVOICE,
                            total_amount=500).model_dump()
        return {"garbage": True}  # missing required fields -> skipped
    monkeypatch.setattr(main, "_extract_file", fake_extract)

    puts: dict[str, object] = {}
    monkeypatch.setattr(main, "_put_json", lambda key, data: puts.__setitem__(key, data))

    main.main()
    docs = puts["extracted/2026-01/up-test/documents.json"]["documents"]
    assert len(docs) == 1
    # No payroll docs -> no events, no validation results.
    assert puts["extracted/2026-01/up-test/events.json"]["events"] == []
    assert puts["extracted/2026-01/up-test/validation.json"]["summary"]["total"] == 0


# ── _extract_file dispatch ────────────────────────────────────────────────────

class _FakeExtractor:
    def __init__(self, suffix, doc=None, boom=False):
        self.suffix, self.doc, self.boom = suffix, doc, boom

    def can_handle(self, path):
        return path.suffix == self.suffix

    def extract(self, path):
        if self.boom:
            raise RuntimeError("extractor failure")
        return self.doc


def test_extract_file_dispatches_to_matching_extractor(monkeypatch):
    monkeypatch.setattr(main, "_download", lambda key, dest: Path(dest).write_bytes(b"%PDF"))
    doc = make_doc(source_file="placeholder", doc_type=DocType.PAYSLIP, total_amount=900)
    monkeypatch.setattr(main, "EXTRACTORS", [_FakeExtractor(".pdf", doc=doc)])
    out = main._extract_file("raw-docs/2026-01/up-test/x.pdf")
    assert out is not None and out["total_amount"] == 900.0


def test_extract_file_returns_none_when_no_extractor(monkeypatch):
    monkeypatch.setattr(main, "_download", lambda key, dest: Path(dest).write_bytes(b"x"))
    monkeypatch.setattr(main, "EXTRACTORS", [_FakeExtractor(".png")])  # cannot handle .xyz
    assert main._extract_file("raw-docs/2026-01/up-test/file.xyz") is None


def test_extract_file_swallows_extractor_error(monkeypatch):
    monkeypatch.setattr(main, "_download", lambda key, dest: Path(dest).write_bytes(b"%PDF"))
    monkeypatch.setattr(main, "EXTRACTORS", [_FakeExtractor(".pdf", boom=True)])
    assert main._extract_file("raw-docs/2026-01/up-test/x.pdf") is None


# ── S3 helpers (boto3 mocked) ─────────────────────────────────────────────────

def test_s3_helpers_hit_boto_client(monkeypatch):
    calls: dict[str, object] = {}

    class _FakePaginator:
        def paginate(self, **kw):
            calls["paginate"] = kw
            yield {"Contents": [
                {"Key": "raw-docs/2026-01/up-test/a.pdf"},
                {"Key": "raw-docs/2026-01/up-test/manifest.json"},
            ]}

    class _FakeClient:
        def get_paginator(self, name):
            calls["paginator"] = name
            return _FakePaginator()

        def download_file(self, bucket, key, dest):
            calls["download"] = (bucket, key, dest)

        def put_object(self, **kw):
            calls["put"] = kw

    monkeypatch.setattr(main.boto3, "client", lambda *a, **k: _FakeClient())

    # _list_raw_files must drop manifest.json.
    assert main._list_raw_files("up-test", "2026-01") == ["raw-docs/2026-01/up-test/a.pdf"]

    main._download("some/key.pdf", Path("dest.pdf"))
    assert calls["download"][1] == "some/key.pdf"

    main._put_json("out/key.json", {"a": 1})
    assert calls["put"]["Key"] == "out/key.json"
    assert calls["put"]["ContentType"] == "application/json"
