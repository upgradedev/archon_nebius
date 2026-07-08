"""
Integration test for the analysis endpoint orchestrator (server.py /analyze).

Drives the full 7-agent chain through the FastAPI app with an in-memory fake S3
(no network) and a stubbed narrator. Verifies the agents are wired in the right
order and the employer-cost fusion survives end to end.
"""
import json

import pytest
from fastapi.testclient import TestClient

import server
from conftest import make_doc


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class _FakePaginator:
    def __init__(self, store):
        self._store = store

    def paginate(self, Bucket, Prefix):
        contents = [{"Key": k} for k in self._store if k.startswith(Prefix)]
        yield {"Contents": contents}


class _FakeS3:
    """Minimal in-memory S3 supporting the calls server.py makes."""

    def __init__(self, store):
        self.store = store

    def get_paginator(self, _name):
        return _FakePaginator(self.store)

    def get_object(self, Bucket, Key):
        if Key not in self.store:
            raise KeyError(Key)
        return {"Body": _FakeBody(self.store[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.store[Key] = Body


@pytest.fixture
def fake_store(monkeypatch):
    store: dict[str, bytes] = {}
    fake = _FakeS3(store)
    monkeypatch.setattr(server, "_s3", lambda: fake)
    monkeypatch.setattr(server, "build_summary", lambda report: "EXEC SUMMARY")
    return store


@pytest.fixture
def client():
    return TestClient(server.app)


def _documents_payload():
    docs = [
        make_doc(source_file="sale.pdf", doc_type="sales", total_amount=20_000),
        make_doc(source_file="reg.pdf", doc_type="payroll_register",
                 total_amount=10_000, employer_cost_total=12_800, net_pay_total=10_000,
                 employee_count=2, gross_pay_total=11_000, recipient_name="My Co"),
        make_doc(source_file="bank.pdf", doc_type="bank_confirmation",
                 total_amount=10_000, issue_date="2026-01-28"),
        make_doc(source_file="s1.pdf", doc_type="payslip", total_amount=5_000, employee_code="E1"),
        make_doc(source_file="s2.pdf", doc_type="payslip", total_amount=5_000, employee_code="E2"),
        make_doc(source_file="stmt.pdf", doc_type="account_statement",
                 vendor_name="DEH", vendor_tax_id="EL999", statement_balance=100.0,
                 statement_entries=[{"document_number": "Z1", "original_amount": 100, "remaining_amount": 0}]),
    ]
    return {"documents": [d.model_dump() for d in docs]}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "archon-analysis"


def test_analyze_full_pipeline(client, fake_store):
    fake_store["extracted/2026-01/u1/documents.json"] = json.dumps(_documents_payload()).encode()

    r = client.post("/analyze", json={"period": "2026-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    report = body["report"]

    # revenue from sales; expense = register employer_cost (fusion), not bank net
    assert report["pnl"]["revenue"] == 20_000.0
    assert report["pnl"]["expenses"] == 12_800.0
    # cash flow uses the real bank transfer (net), not employer cost
    assert report["cashFlow"]["operating"] == 10_000.0
    # employee + payroll-event analytics produced
    assert len(report["employeeSummaries"]) == 2
    assert report["payrollEvents"][0]["employee_count"] == 2
    # account_statement excluded from P&L but drives reconciliation
    assert len(report["vendorReconciliations"]) == 1
    assert report["executiveSummary"] == "EXEC SUMMARY"
    # report was cached back to storage
    assert "reports/2026-01/report.json" in fake_store


def test_analyze_404_when_no_documents(client, fake_store):
    r = client.post("/analyze", json={"period": "2099-12"})
    assert r.status_code == 404


def test_analyze_skips_malformed_document(client, fake_store):
    payload = {"documents": [{"bogus": "no required fields"},
                             make_doc(doc_type="sales", total_amount=500).model_dump()]}
    fake_store["extracted/2026-03/u1/documents.json"] = json.dumps(payload).encode()
    r = client.post("/analyze", json={"period": "2026-03"})
    assert r.status_code == 200
    assert r.json()["report"]["pnl"]["revenue"] == 500.0


def test_get_report_roundtrip(client, fake_store):
    # analyze first so a complete, response-model-valid report is cached
    fake_store["extracted/2026-01/u1/documents.json"] = json.dumps(_documents_payload()).encode()
    assert client.post("/analyze", json={"period": "2026-01"}).status_code == 200
    r = client.get("/reports/2026-01")
    assert r.status_code == 200
    assert r.json()["report"]["period"] == "2026-01"


def test_get_report_404(client, fake_store):
    r = client.get("/reports/1999-01")
    assert r.status_code == 404
