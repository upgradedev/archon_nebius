"""
Archon evaluation harness — runner.

Scores the REAL extraction + analysis agents against a labelled corpus and
prints the four accuracy metrics plus the payroll document-value comparison. Writes
machine-readable results to eval/RESULTS.json.

Usage:
    python eval/evaluate.py                             # corpus/sample (default)
    python eval/evaluate.py eval/corpus/full            # positional corpus dir
    python eval/evaluate.py --corpus eval/corpus/full   # same, named flag
    python eval/evaluate.py --corpus eval/corpus/full --out eval/RESULTS_full.json

The committed 40-case `eval/corpus/full/` + `eval/RESULTS_full.json` regenerate
the headline accuracy table offline (no API key, only `pydantic`):

    python eval/generate_corpus.py --out corpus/full --n 40 --seed 7
    python eval/evaluate.py --corpus eval/corpus/full --out eval/RESULTS_full.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # make `lib` importable

from lib.corpus import load_corpus           # noqa: E402
from lib.extractors import perfect_extractor, degraded_extractor  # noqa: E402
from lib import metrics                       # noqa: E402


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the real Archon agents against a labelled corpus.")
    ap.add_argument("corpus_pos", nargs="?", default=None,
                    help="corpus dir (positional; back-compat with `evaluate.py eval/corpus/full`)")
    ap.add_argument("--corpus", default=None, help="corpus dir (default: eval/corpus/sample)")
    ap.add_argument("--out", default=None,
                    help="results JSON path (default: eval/RESULTS.json)")
    args = ap.parse_args()

    corpus_dir = args.corpus or args.corpus_pos or "eval/corpus/sample"
    cases = load_corpus(corpus_dir)

    ceiling = metrics.run_extractor(cases, perfect_extractor)
    degraded = metrics.run_extractor(cases, degraded_extractor)
    floor = metrics.naive_floor(cases)

    print(f"\nArchon evaluation harness - corpus: {corpus_dir} ({len(cases)} cases)\n")
    print(f"{'Metric':<26}{'Ceiling (perfect)':<22}{'Degraded':<14}")
    print("-" * 62)
    rows = [
        ("Classification accuracy", "classification"),
        ("Field accuracy", "field"),
        ("Fusion figure accuracy", "fusion"),
        ("Validation-outcome acc.", "validation"),
    ]
    for label, key in rows:
        c = _pct(ceiling[key]["accuracy"])
        d = _pct(degraded[key]["accuracy"])
        print(f"{label:<26}{c:<22}{d:<14}")

    print("\nRule activity at the ceiling (fired vs skipped on applicable cases):")
    for rid, a in ceiling["validation"]["rule_activity"].items():
        app, fired = a["applicable"], a["fired"]
        state = "DORMANT" if app and fired == 0 else ("active" if fired else "n/a")
        print(f"  {rid}: fired {fired}/{app} applicable cases  -> {state}")

    print("\nValidation-outcome divergences (perfect inputs, pipeline vs domain truth):")
    if ceiling["validation"]["divergences"]:
        for dv in ceiling["validation"]["divergences"]:
            print(f"  - {dv['case']} {dv['rule']}: expected_pass={dv['expected_pass']} "
                  f"actual_pass={dv['actual_pass']}  ({dv['detail']})")
    else:
        print("  (none)")

    print("\nPayroll document comparison (bank-confirmed net wages vs register employer cost):")
    if floor["cases"]:
        print(f"  cases with a bank doc           {floor['cases']}")
        print(f"  total bank-confirmed net wages  EUR {floor['total_bank_only']:,.2f}")
        print(f"  total register employer cost    EUR {floor['total_true_cost']:,.2f}")
        print(f"  total numeric difference         EUR {floor['total_understatement']:,.2f}")
        print(f"  mean difference % of register   {floor['mean_understatement_pct_of_true']}%")
        print(f"  mean difference % of bank net   {floor['mean_understatement_pct_of_bank']}%")
        print(f"  mean employer-contribution component % bank  {floor['mean_employer_social_security_wedge_pct_of_bank']}%")
        print("  note: complementary document values; not proof of separate liability payments")

    out = Path(args.out) if args.out else Path(__file__).resolve().parent / "RESULTS.json"
    out.write_text(json.dumps(
        {"corpus": corpus_dir, "ceiling": ceiling, "degraded": degraded, "naive_floor": floor},
        indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
