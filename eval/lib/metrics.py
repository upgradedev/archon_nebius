"""
Metrics for the Archon evaluation harness.

Every metric scores the REAL pipeline agents (ClassifierAgent, EventLinkerAgent,
ValidatorAgent, PnLAgent) against the free ground-truth labels — never a
re-implementation.

  1. classification accuracy  — doc_type after the real ClassifierAgent vs truth
  2. field accuracy           — extracted totals/dates vs truth
  3. validation outcome       — R1-R4 from the real ValidatorAgent vs DOMAIN truth
  4. fusion figure accuracy   — the payroll expense the real PnLAgent reports
                                (+ bank net, employee count) vs truth
  5. naive floor              — bank-only payroll cost vs true employer cost

Because the two pipelines ship colliding `models` packages, scoring runs in two
isolated phases: all extraction-side work first, snapshot the per-doc fields,
then load the analysis pipeline for the P&L figure. See `lib/loader.py`.
"""

from __future__ import annotations

from . import loader

NUM_REL_TOL = 0.005  # 0.5%


def num_match(expected: float, actual, rel_tol: float = NUM_REL_TOL) -> bool:
    if actual is None:
        return False
    try:
        actual = float(actual)
    except (TypeError, ValueError):
        return False
    if abs(expected - actual) <= 0.01:
        return True
    if expected == 0:
        return abs(actual) <= 0.01
    return abs(expected - actual) / abs(expected) <= rel_tol


def _rule_id(rule: str) -> str:
    return rule.split(":", 1)[0].strip()


def run_extractor(cases: list[dict], extractor_fn) -> dict:
    """
    Run `extractor_fn(ext_modules, case) -> list[ExtractedDocument]` over every
    case through the real agents and return aggregated + per-case scores.
    """
    ext = loader.load_extraction()
    classifier = ext["agents.classifier"]
    event_linker = ext["agents.event_linker"]
    validator = ext["agents.validator"]

    cls_total = cls_correct = 0
    cls_errors: list[dict] = []
    fld_total = fld_correct = 0
    val_total = val_correct = 0
    val_divergences: list[dict] = []
    # rule activity: of the cases where a rule COULD apply (its inputs present),
    # how often did it actually evaluate vs skip? A rule that skips on 100% of
    # applicable cases is dormant (its inputs are never extracted).
    activity = {r: {"applicable": 0, "fired": 0} for r in ("R1", "R2", "R3", "R4")}
    snapshots: list[dict] = []   # per-case analysis input + expectations

    for case in cases:
        docs = extractor_fn(ext, case)
        docs = classifier.run(docs)                      # REAL ClassifierAgent
        by_src = {d.source_file: d for d in docs}

        # 1. classification
        for label in case["documents"]:
            cls_total += 1
            got = by_src.get(label["source_file"])
            actual = got.doc_type.value if got else "MISSING"
            if actual == label["doc_type"]:
                cls_correct += 1
            else:
                cls_errors.append({"case": case["case_id"], "src": label["source_file"],
                                   "expected": label["doc_type"], "actual": actual})

        # 2. field accuracy (the fields the current prompt emits)
        for label in case["documents"]:
            got = by_src.get(label["source_file"])
            if "total_amount" in label:
                fld_total += 1
                if got and num_match(label["total_amount"], got.total_amount):
                    fld_correct += 1
            if label.get("issue_date"):
                fld_total += 1
                if got and got.issue_date == label["issue_date"]:
                    fld_correct += 1

        # 3. validation outcome — REAL EventLinker + Validator
        events = event_linker.run(docs)
        results = validator.run(events)
        by_rule = {_rule_id(r.rule): r for r in results}
        mix = case["document_mix"]
        applicable = {
            "R1": mix["bank"] and mix["payslips_emitted"] > 0,
            "R2": mix["register"],
            "R3": mix["bank"],
            "R4": mix["register"] and mix["payslips_emitted"] > 0,
        }
        for rid in ("R1", "R2", "R3", "R4"):
            val_total += 1
            expected = case["expected_validations"][rid]
            res = by_rule.get(rid)
            actual = res.passed if res else True
            fired = bool(res) and not res.message.startswith("Skipped")
            if applicable[rid]:
                activity[rid]["applicable"] += 1
                if fired:
                    activity[rid]["fired"] += 1
            if actual == expected:
                val_correct += 1
            else:
                val_divergences.append({
                    "case": case["case_id"], "rule": rid,
                    "expected_pass": expected, "actual_pass": actual,
                    "detail": res.message if res else "rule not produced",
                })

        # snapshot analysis input from the classified docs (plain values —
        # survives the module purge in phase B)
        snap_docs = [{
            "source_file": d.source_file,
            "doc_type": d.doc_type.value,
            "detected_language": d.detected_language,
            "issue_date": d.issue_date,
            "vendor_name": d.vendor_name,
            "vendor_tax_id": d.vendor_tax_id,
            "recipient_name": d.recipient_name,
            "currency": d.currency,
            "subtotal": d.subtotal,
            "vat_amount": d.vat_amount,
            "vat_rate_pct": d.vat_rate_pct,
            "total_amount": d.total_amount,
            "payment_due_date": d.payment_due_date,
            "invoice_number": d.invoice_number,
            "notes": d.notes,
            "confidence": d.confidence,
            "employer_cost_total": d.employer_cost_total,
            "net_pay_total": d.net_pay_total,
            "employee_count": d.employee_count,
            "gross_pay_total": d.gross_pay_total,
        } for d in docs]
        snapshots.append({"case": case, "docs": snap_docs})

    # ── phase B: analysis pipeline (purges extraction modules) ────────────────
    ana = loader.load_analysis()
    ExtractedDoc = ana["models.financial"].ExtractedDoc
    pnl_agent = ana["agents.pnl_agent"]

    fig_total = fig_correct = 0
    fig_detail: list[dict] = []
    for snap in snapshots:
        case = snap["case"]
        mix = case["document_mix"]
        ana_docs = [ExtractedDoc(**d) for d in snap["docs"]]
        pnl = pnl_agent.build_pnl(case["period"], ana_docs)

        # employer-cost fusion is only meaningful when a register is present
        if mix["register"]:
            exp = case["expected_figures"]["employer_cost_total"]
            fig_total += 1
            ok = num_match(exp, pnl.expenses)
            if ok:
                fig_correct += 1
            fig_detail.append({"case": case["case_id"], "figure": "payroll_expense",
                               "expected": exp, "actual": pnl.expenses, "match": ok})

    return {
        "extractor": getattr(extractor_fn, "__name__", str(extractor_fn)),
        "cases": len(cases),
        "classification": {"total": cls_total, "correct": cls_correct,
                           "accuracy": _acc(cls_correct, cls_total), "errors": cls_errors},
        "field": {"total": fld_total, "correct": fld_correct,
                  "accuracy": _acc(fld_correct, fld_total)},
        "validation": {"total": val_total, "correct": val_correct,
                       "accuracy": _acc(val_correct, val_total),
                       "divergences": val_divergences,
                       "rule_activity": activity},
        "fusion": {"total": fig_total, "correct": fig_correct,
                   "accuracy": _acc(fig_correct, fig_total), "detail": fig_detail},
    }


def naive_floor(cases: list[dict]) -> dict:
    """Bank-only payroll cost vs true employer cost — the value the product recovers."""
    rows = [c["naive"] for c in cases if c.get("naive")]
    n = len(rows)
    if not n:
        return {"cases": 0}
    bank = sum(r["bank_only_payroll_cost"] for r in rows)
    true_cost = sum(r["true_employer_cost"] for r in rows)
    under = sum(r["understatement_amount"] for r in rows)
    return {
        "cases": n,
        "total_bank_only": round(bank, 2),
        "total_true_cost": round(true_cost, 2),
        "total_understatement": round(under, 2),
        "mean_understatement_pct_of_true": round(sum(r["understatement_pct_of_true"] for r in rows) / n, 2),
        "mean_understatement_pct_of_bank": round(sum(r["understatement_pct_of_bank"] for r in rows) / n, 2),
        "mean_employer_ika_wedge_pct_of_bank": round(sum(r["employer_ika_wedge_pct_of_bank"] for r in rows) / n, 2),
        "max_understatement_pct_of_bank": round(max(r["understatement_pct_of_bank"] for r in rows), 2),
    }


def _acc(correct: int, total: int) -> float:
    return round(correct / total, 4) if total else 1.0
