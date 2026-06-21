"""Stage 3 — dashboard-facing endpoints reflect the completed pipeline,
and period lifecycle (list / fetch / delete) behaves.

Ordered last (test_04_) so the delete test runs after the pipeline assertions.
"""
import pytest


def test_period_listed_with_flags(http, base_url, completed_pipeline, period):
    r = http.get(f"{base_url}/api/periods", timeout=30)
    assert r.status_code == 200
    by_period = {p["period"]: p for p in r.json()}
    assert period in by_period, f"{period} not listed in /api/periods"
    entry = by_period[period]
    assert entry["hasExtraction"] is True
    assert entry["hasReport"] is True


def test_documents_endpoint_matches_pipeline(http, base_url, completed_pipeline, period):
    r = http.get(f"{base_url}/api/documents/{period}", timeout=30)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) == len(completed_pipeline["documents"])


def test_report_endpoint_matches_pipeline(http, base_url, completed_pipeline, period):
    r = http.get(f"{base_url}/api/reports/{period}", timeout=30)
    assert r.status_code == 200
    envelope = r.json()
    report = envelope.get("report", envelope)
    assert report["period"] == period


@pytest.mark.parametrize("bad", ["2026-13", "../x", "nope"])
def test_documents_endpoint_validates_period(http, base_url, bad):
    assert http.get(f"{base_url}/api/documents/{bad}", timeout=30).status_code in (404, 422)


def test_zzz_delete_period_is_clean(http, base_url, completed_pipeline, period):
    """Runs last: deleting the period removes raw-docs/extracted/reports and the
    period drops out of the listing.
    """
    d = http.delete(f"{base_url}/api/periods/{period}", timeout=60)
    assert d.status_code == 200
    body = d.json()
    assert body["period"] == period
    assert body["deleted"] >= 1

    listed = {p["period"] for p in http.get(f"{base_url}/api/periods", timeout=30).json()}
    assert period not in listed, "period still listed after delete"
    assert http.get(f"{base_url}/api/reports/{period}", timeout=30).status_code == 404
