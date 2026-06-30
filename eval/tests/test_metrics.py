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


def test_active_rules_fire_and_are_correct(ceiling):
    act = ceiling["validation"]["rule_activity"]
    # R1 (bank vs payslips) and R3 (payment date) are wired end-to-end
    assert act["R1"]["fired"] == act["R1"]["applicable"] > 0
    assert act["R3"]["fired"] == act["R3"]["applicable"] > 0


def test_R2_and_R4_are_dormant(ceiling):
    # KEYSTONE FINDING: R2 and R4 never fire because the extractor never
    # populates employer_cost_total / net_pay_total / employee_count
    # (see jobs/extraction/extractors/image.py::EXTRACTION_PROMPT).
    act = ceiling["validation"]["rule_activity"]
    assert act["R2"]["applicable"] > 0 and act["R2"]["fired"] == 0, "R2 expected dormant"
    assert act["R4"]["applicable"] > 0 and act["R4"]["fired"] == 0, "R4 expected dormant"


def test_dormant_R4_misses_a_real_defect(ceiling):
    # the missing-payslip case is a genuine inconsistency; R4 should catch it but
    # cannot (dormant) -> it surfaces as a validation-outcome divergence
    divs = {(d["case"], d["rule"]) for d in ceiling["validation"]["divergences"]}
    assert any(rule == "R4" for _case, rule in divs)


def test_active_R1_does_catch_a_real_defect(ceiling):
    # the same missing-payslip case is caught by R1 (amount mismatch) -> no R1
    # divergence; proves an active rule earns its place
    divs = {(d["case"], d["rule"]) for d in ceiling["validation"]["divergences"]}
    assert not any(rule == "R1" for _case, rule in divs)


def test_metrics_discriminate(ceiling, degraded):
    # a weak extractor must score measurably below the ceiling, and fusion must
    # collapse faster than field accuracy (errors compound through the sums)
    assert degraded["field"]["accuracy"] < ceiling["field"]["accuracy"]
    assert degraded["fusion"]["accuracy"] < degraded["field"]["accuracy"]


def test_naive_floor_quantifies_the_value(cases):
    floor = metrics.naive_floor(cases)
    assert floor["cases"] >= 1
    assert floor["total_understatement"] > 0
    # the headline employer-IKA wedge is a meaningful fraction of the bank figure
    assert floor["mean_employer_ika_wedge_pct_of_bank"] > 10
