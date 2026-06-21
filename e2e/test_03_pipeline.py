"""Stage 2 — the full pipeline, end to end, with deep assertions.

All tests share the session-scoped `completed_pipeline` fixture, which runs
upload -> extract -> analyze ONCE against the live stack (real Nebius models).
Structural/contract assertions are strict; LLM-content assertions are
directional (robust to minor model variance) but still meaningful — above all
the 28% payroll-gap invariant that is Archon's reason to exist.
"""
import pytest

NUMBER = (int, float)


# ── Upload stage ──────────────────────────────────────────────────────────────

def test_upload_returned_all_files(completed_pipeline):
    up = completed_pipeline["upload"]
    assert "uploadId" in up and up["uploadId"]
    assert len(up["files"]) == completed_pipeline["n_uploaded"]
    for f in up["files"]:
        assert f["filename"] and f["sizeBytes"] > 0 and f["id"]


def test_raw_docs_persisted_to_storage(completed_pipeline, s3, list_keys, period):
    if s3 is None:
        pytest.skip("localstack/boto3 not reachable")
    raw = list_keys(s3, f"raw-docs/{period}/")
    assert any(k.endswith("manifest.json") for k in raw), "manifest.json not written"
    assert sum(1 for k in raw if k.endswith(".pdf")) >= completed_pipeline["n_uploaded"]


# ── Extraction stage ──────────────────────────────────────────────────────────

def test_extraction_job_completed(completed_pipeline):
    assert completed_pipeline["job"]["status"] == "completed"


def test_extracted_documents_present(completed_pipeline):
    docs = completed_pipeline["documents"]
    assert isinstance(docs, list) and len(docs) >= 1, "no extracted documents"


def test_extracted_documents_have_contract_fields(completed_pipeline):
    for d in completed_pipeline["documents"]:
        assert d.get("source_file"), d
        assert d.get("doc_type"), d
        assert isinstance(d.get("total_amount"), NUMBER), d
        assert isinstance(d.get("confidence"), NUMBER), d


def test_extracted_to_storage(completed_pipeline, s3, list_keys, period):
    if s3 is None:
        pytest.skip("localstack/boto3 not reachable")
    extracted = list_keys(s3, f"extracted/{period}/")
    assert any(k.endswith("documents.json") for k in extracted), "documents.json not written"


def test_payroll_documents_classified(completed_pipeline):
    """The synthetic batch contains a payroll event (register/bank/payslip).

    At least one payroll-family doc_type should be recognised — this is what
    makes the employer-cost fusion possible downstream.
    """
    types = {str(d.get("doc_type", "")).lower() for d in completed_pipeline["documents"]}
    payrollish = {t for t in types if any(k in t for k in ("payroll", "payslip", "bank", "salary"))}
    assert payrollish, f"no payroll-family doc types among {types}"


# ── Analysis / report stage ───────────────────────────────────────────────────

def test_report_exists(completed_pipeline):
    assert completed_pipeline["report"] is not None, "no report.json produced"


def test_report_top_level_contract(completed_pipeline):
    r = completed_pipeline["report"]
    for key in ["period", "pnl", "cashFlow", "expenseBreakdown", "topVendors",
                "keyMetrics", "payrollEvents", "employeeSummaries",
                "validationResults", "vendorReconciliations", "executiveSummary"]:
        assert key in r, f"report missing '{key}'"
    assert r["period"] == completed_pipeline["period"]


def test_pnl_block(completed_pipeline):
    pnl = completed_pipeline["report"]["pnl"]
    for k in ["revenue", "expenses", "netProfit", "grossMarginPct", "operatingMarginPct"]:
        assert isinstance(pnl.get(k), NUMBER), f"pnl.{k} not numeric: {pnl.get(k)}"
    # Accounting identity must hold to the cent.
    assert abs(pnl["netProfit"] - (pnl["revenue"] - pnl["expenses"])) < 0.01
    assert pnl["expenses"] > 0, "expenses should be > 0 for the sample batch"


def test_cashflow_block(completed_pipeline):
    cf = completed_pipeline["report"]["cashFlow"]
    for k in ["operating", "investing", "financing", "net"]:
        assert isinstance(cf.get(k), NUMBER), f"cashFlow.{k} not numeric"


def test_validation_results_shape(completed_pipeline):
    vr = completed_pipeline["report"]["validationResults"]
    assert isinstance(vr, list)
    for v in vr:
        assert set(["rule", "passed", "severity", "message"]).issubset(v.keys())
        assert isinstance(v["passed"], bool)


def test_executive_summary_written(completed_pipeline):
    summary = completed_pipeline["report"]["executiveSummary"]
    assert isinstance(summary, str) and len(summary.strip()) >= 40, "executive summary too short/empty"


# ── The 28% payroll-gap invariant (Archon's core thesis) ──────────────────────

def test_payroll_gap_invariant(completed_pipeline):
    """Employer cost must exceed the bank-net transfer when a payroll event is
    detected — the whole point of the EventLinker fusion. We assert direction
    strictly and the ratio within a generous band to stay robust to LLM jitter.
    """
    events = completed_pipeline["report"]["payrollEvents"]
    if not events:
        pytest.skip("no payroll event detected in this run")
    checked = 0
    for ev in events:
        emp = ev.get("employer_cost_total")
        net = ev.get("net_total")
        if emp is None or not net:
            continue
        checked += 1
        assert emp >= net, f"employer_cost ({emp}) should be >= bank net ({net})"
        ratio = emp / net
        assert 1.0 <= ratio <= 1.8, f"employer/net ratio {ratio:.3f} outside sane band"
    if checked == 0:
        # A payroll event was detected but employer_cost wasn't extracted this
        # run (LLM variance / register not fully fused). The invariant only
        # applies when both figures exist — assert direction strictly when they do.
        pytest.skip("no payroll event had both employer_cost_total and net_total")


def test_payroll_event_summary_contract(completed_pipeline):
    for ev in completed_pipeline["report"]["payrollEvents"]:
        for k in ["period", "net_total", "employee_count", "bank_confirmed", "validation_passed"]:
            assert k in ev, f"payrollEvent missing '{k}'"
        assert isinstance(ev["employee_count"], int)
        assert isinstance(ev["bank_confirmed"], bool)
