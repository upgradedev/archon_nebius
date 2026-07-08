"""
Proof-of-execution tests for the Archon evaluation harness.

These run the REAL pipeline agents (ClassifierAgent, EventLinkerAgent,
ValidatorAgent, PnLAgent) over the committed sample corpus and assert concrete
outputs — so CI fails if the pipeline's behaviour regresses, and the numbers in
eval/BASELINE.md stay honest. No network, no API key: only `pydantic`.
"""

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_DIR))

from lib.corpus import load_corpus          # noqa: E402
from lib.extractors import perfect_extractor, degraded_extractor  # noqa: E402
from lib import metrics                      # noqa: E402

CORPUS = EVAL_DIR / "corpus" / "sample"


@pytest.fixture(scope="module")
def cases():
    return load_corpus(CORPUS)


@pytest.fixture(scope="module")
def ceiling(cases):
    return metrics.run_extractor(cases, perfect_extractor)


@pytest.fixture(scope="module")
def degraded(cases):
    return metrics.run_extractor(cases, degraded_extractor)


def test_corpus_present(cases):
    assert len(cases) >= 6


def test_ceiling_perfect_on_extracted_fields(ceiling):
    # perfect extraction of what the current prompt emits -> 100% on the things
    # the product can actually know
    assert ceiling["classification"]["accuracy"] == 1.0
    assert ceiling["field"]["accuracy"] == 1.0
    assert ceiling["fusion"]["accuracy"] == 1.0   # P&L reports employer cost, not bank net


def test_all_four_rules_fire_and_are_correct(ceiling):
    # All four rules are wired end-to-end and evaluate on every applicable case.
    # R2/R4 were dormant until the extractor was taught to populate
    # employer_cost_total / net_pay_total / gross_pay_total / employee_count
    # (jobs/extraction/extractors/image.py::EXTRACTION_PROMPT); they now fire.
    act = ceiling["validation"]["rule_activity"]
    for rid in ("R1", "R2", "R3", "R4"):
        assert act[rid]["fired"] == act[rid]["applicable"] > 0, f"{rid} expected active"


def test_R2_and_R4_now_active(ceiling):
    # RESOLVED (was the keystone dormancy bug): with the payroll fields extracted,
    # R2 (employer-cost ratio) and R4 (headcount) evaluate instead of skipping.
    act = ceiling["validation"]["rule_activity"]
    assert act["R2"]["applicable"] > 0 and act["R2"]["fired"] == act["R2"]["applicable"], "R2 expected active"
    assert act["R4"]["applicable"] > 0 and act["R4"]["fired"] == act["R4"]["applicable"], "R4 expected active"


def test_ceiling_reproduces_domain_truth_on_all_rules(ceiling):
    # With R2/R4 active, perfect extraction matches domain truth on all four
    # rules across the corpus -> zero divergences, 100% validation-outcome.
    # In particular R4 now catches the missing-payslip case it used to miss.
    assert ceiling["validation"]["divergences"] == []
    assert ceiling["validation"]["accuracy"] == 1.0


def test_active_R1_and_R4_both_catch_the_missing_payslip_defect(ceiling):
    # the missing-payslip case (register reports N, only N-1 payslips) is a
    # genuine inconsistency. R1 (amount mismatch) always caught it; R4 (headcount)
    # now catches it too -> neither produces a divergence against domain truth.
    divs = {(d["case"], d["rule"]) for d in ceiling["validation"]["divergences"]}
    assert not any(rule == "R1" for _case, rule in divs)
    assert not any(rule == "R4" for _case, rule in divs)


def test_degraded_R2_catches_structural_extraction_error(degraded):
    # R2 earns its place: a structural net-line misread on the register (the
    # degraded extractor sets net_pay_total = gross) pushes employer_cost/net
    # below the [1.40, 2.60] band, so R2 fires and flags the corrupted
    # extraction -> an R2 divergence the perfect extractor never produces.
    divs = {(d["case"], d["rule"]) for d in degraded["validation"]["divergences"]}
    assert any(rule == "R2" for _case, rule in divs), "R2 should catch the structural net-line misread"


def test_metrics_discriminate(ceiling, degraded):
    # a weak extractor must score measurably below the ceiling, and fusion must
    # collapse faster than field accuracy (errors compound through the sums)
    assert degraded["field"]["accuracy"] < ceiling["field"]["accuracy"]
    assert degraded["fusion"]["accuracy"] < degraded["field"]["accuracy"]


def test_naive_floor_quantifies_the_value(cases):
    floor = metrics.naive_floor(cases)
    assert floor["cases"] >= 1
    assert floor["total_understatement"] > 0
    # the headline employer social-security wedge is a meaningful fraction of the bank figure
    assert floor["mean_employer_social_security_wedge_pct_of_bank"] > 10
