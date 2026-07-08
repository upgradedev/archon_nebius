"""
Archon evaluation harness — labelled corpus generator.

Emits, per case, a `ground_truth.json` carrying:
  * `documents`  — the fields a *perfect* extractor would return under the
    CURRENT production extraction prompt (generic fields only — see
    `jobs/extraction/extractors/image.py::EXTRACTION_PROMPT`). These are what
    the harness feeds to the REAL classifier / event-linker / validator / P&L
    agents.
  * `truth`      — the full payroll truth we know because we synthesised it
    (gross, employee/employer social-security, tax, per-employee rows). Free
    ground truth.
  * `expected_validations` — domain truth for R1–R4 (is this payroll actually
    consistent?), kept SEPARATE from the figures so a rule bug cannot hide.
  * `expected_figures`     — the fused numbers the product should report.
  * `naive`      — the bank-only "payroll cost" an owner would book, and the
    understatement vs the true employer cost (the value the product recovers).

The small `corpus/sample/` set is committed (JSON only — no PDFs, no deps) and
reproduces every baseline offline. Pass `--pdf` to additionally render the
documents to PDF (needs `pip install reportlab`) for the live-extraction slot
(see `eval/LIVE_EXTRACTION.md`); rendered PDFs are gitignored.

Usage:
    python eval/generate_corpus.py                 # rewrite corpus/sample/*.json
    python eval/generate_corpus.py --pdf           # also render PDFs
    python eval/generate_corpus.py --out corpus/full --n 40 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from calendar import monthrange
from datetime import date
from pathlib import Path

# ── payroll arithmetic (single source of truth) ───────────────────────────────
EMPLOYEE_SOCIAL_SECURITY_RATE = 0.16   # employee social-security withholding
TAX_RATE = 0.11                        # PAYE income-tax withholding
EMPLOYER_SOCIAL_SECURITY_RATE = 0.26   # employer social-security contribution (the hidden cost)

# Locale-neutral, mixed-locale sample entities. List LENGTHS are load-bearing:
# `rng.choice` consumes a length-dependent amount of the RNG stream, so keeping
# the counts (12 / 12 / 10) unchanged keeps every downstream numeric draw -- and
# thus every committed amount and baseline metric -- byte-for-byte identical.
COMPANIES = [
    "Northwind Foods Ltd", "Pinnacle Logistics GmbH", "Cyan Software SA",
    "Summit Retail Inc", "Terra Agro BV", "Meridian Services Srl",
    "Cobalt Build Oy", "Coral Tourism AB", "Ferrum Metals NV",
    "Valley Dairy SAS", "Harbor Marine Pty", "Delta Trade Sp. z o.o.",
]
FIRST = ["Maria", "James", "Wei", "Sofia", "Omar", "Anders",
         "Priya", "Lucas", "Hana", "Diego", "Yuki", "Nina"]
LAST = ["Andersen", "Smith", "Kim", "Rossi", "Novak",
        "Haddad", "Nakamura", "Silva", "Meyer", "Okafor"]


def _employee(emp_id: str, gross: float) -> dict:
    employee_ss = round(gross * EMPLOYEE_SOCIAL_SECURITY_RATE, 2)
    tax = round(gross * TAX_RATE, 2)
    net = round(gross - employee_ss - tax, 2)
    employer_ss = round(gross * EMPLOYER_SOCIAL_SECURITY_RATE, 2)
    employer_cost = round(gross + employer_ss, 2)
    return {
        "employee_code": emp_id, "gross": gross,
        "employee_social_security": employee_ss,
        "tax": tax, "net": net, "employer_social_security": employer_ss,
        "employer_cost": employer_cost,
    }


def _last_day(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return date(y, m, monthrange(y, m)[1]).isoformat()


def build_case(case_id: str, rng: random.Random, edge_cases: list[str] | None = None) -> dict:
    edge_cases = edge_cases or []
    company = rng.choice(COMPANIES)
    year = rng.choice([2025, 2026])
    month = rng.randint(1, 12)
    period = f"{year:04d}-{month:02d}"
    pay_date = _last_day(period)

    n_emp = rng.randint(1, 6) if "single_employee" not in edge_cases else 1
    employees = []
    for i in range(n_emp):
        gross = round(rng.uniform(850, 4200), 2)
        emp = _employee(f"EMP-{i + 1:03d}", gross)
        emp["name"] = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        employees.append(emp)

    gross_total = round(sum(e["gross"] for e in employees), 2)
    employee_social_security_total = round(sum(e["employee_social_security"] for e in employees), 2)
    tax_total = round(sum(e["tax"] for e in employees), 2)
    employer_social_security_total = round(sum(e["employer_social_security"] for e in employees), 2)
    employer_cost_total = round(sum(e["employer_cost"] for e in employees), 2)
    net_total = round(sum(e["net"] for e in employees), 2)

    has_bank = "missing_bank" not in edge_cases
    has_register = "missing_register" not in edge_cases
    # missing_payslip: the bank/register reflect N, but only N-1 payslips on file
    payslips_emitted = n_emp - 1 if "missing_payslip" in edge_cases else n_emp

    # bank net the company actually transferred (the "wrong" cost an owner books)
    bank_net = net_total
    if "bank_mismatch" in edge_cases:
        bank_net = round(net_total * 1.06, 2)   # +6% reconciliation break -> R1 fails

    bank_issue_date = pay_date
    if "late_payment" in edge_cases:
        # paid in the following month -> R3 fails
        ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
        bank_issue_date = f"{ny:04d}-{nm:02d}-05"

    # ── documents = perfect extraction under the CURRENT prompt ──────────────────
    # The production prompt (jobs/extraction/extractors/image.py::EXTRACTION_PROMPT)
    # now requests the payroll fields (gross_pay_total / employer_cost_total /
    # net_pay_total / employee_count) on the register + net_pay_total on the bank
    # confirmation. These labels mirror exactly what a perfect read of that prompt
    # returns, so the ceiling stays the real product's ceiling — and R2/R4, which
    # read those fields, are now live rather than dormant.
    documents: list[dict] = []
    if has_bank:
        documents.append({
            "source_file": f"bank_confirmation_{period}.pdf",
            "doc_type": "bank_confirmation",
            "detected_language": "en",
            "issue_date": bank_issue_date,
            "recipient_name": company,
            "vendor_name": "Zenith Bank",
            "currency": "EUR",
            "total_amount": bank_net,
            "net_pay_total": bank_net,        # the net amount actually transferred
            "notes": "Batch payroll transfer confirmation",
            "raw_text_excerpt": "ZENITH BANK BATCH PAYROLL TRANSFER CONFIRMATION",
        })
    if has_register:
        documents.append({
            "source_file": f"payroll_register_{period}.pdf",
            "doc_type": "payroll_register",
            "detected_language": "en",
            "issue_date": pay_date,
            "recipient_name": company,
            "vendor_name": company,
            "currency": "EUR",
            # Best-case perfect read: the register's headline total is the
            # employer cost (gross + employer social-security). See BASELINE.md
            # §4 for why this is the *only* economically-correct reading. The
            # explicit payroll fields below are what R2/R4 and the P&L agent read
            # (the P&L now prefers employer_cost_total over total_amount).
            "total_amount": employer_cost_total,
            "gross_pay_total": gross_total,
            "employer_cost_total": employer_cost_total,
            "net_pay_total": net_total,
            "employee_count": n_emp,          # register reports the full headcount
            "notes": "Payroll register - employer social-security contributions - total employer cost",
            "raw_text_excerpt": "PAYROLL REGISTER EMPLOYER SOCIAL SECURITY CONTRIBUTIONS TOTAL EMPLOYER COST",
        })
    for e in employees[:payslips_emitted]:
        documents.append({
            "source_file": f"payslip_{e['employee_code']}_{period}.pdf",
            "doc_type": "payslip",
            "detected_language": "en",
            "issue_date": pay_date,
            "recipient_name": company,
            "vendor_name": company,
            "currency": "EUR",
            "total_amount": e["net"],          # payslip headline total = net pay
            "employee_name": e["name"],
            "employee_code": e["employee_code"],
            "notes": "Payslip - net pay",
            "raw_text_excerpt": "PAYSLIP net pay",
        })

    # ── domain truth for the four rules (is this payroll actually consistent?) ──
    # R1: bank net == sum(payslip nets) within 2%
    slips_net = round(sum(e["net"] for e in employees[:payslips_emitted]), 2)
    r1 = has_bank and payslips_emitted > 0 and abs(bank_net - slips_net) / slips_net <= 0.02
    if not has_bank or payslips_emitted == 0:
        r1 = True   # rule correctly skips -> treated as pass
    # R2: employer_cost / net ratio is a legitimate payroll ratio (~1.73), which
    #     sits inside the recalibrated [1.40, 2.60] band. Domain truth =
    #     consistent (pass). R2 fires on every register now; the degraded
    #     extractor (a structural net-line misread) is what makes it fail.
    r2 = True
    # R3: payment date on/before period end
    r3 = True
    if has_bank and "late_payment" in edge_cases:
        r3 = False
    # R4: register headcount == payslips on file
    r4 = True
    if has_register and "missing_payslip" in edge_cases:
        r4 = False

    naive = None
    if has_bank:
        understatement = round(employer_cost_total - bank_net, 2)
        naive = {
            "bank_only_payroll_cost": bank_net,
            "true_employer_cost": employer_cost_total,
            "understatement_amount": understatement,
            "understatement_pct_of_true": round(understatement / employer_cost_total * 100, 2),
            "understatement_pct_of_bank": round(understatement / bank_net * 100, 2),
            "employer_social_security_wedge_pct_of_bank": round(employer_social_security_total / bank_net * 100, 2),
        }

    return {
        "case_id": case_id,
        "company": company,
        "period": period,
        "payment_date": pay_date,
        "edge_cases": edge_cases,
        "document_mix": {
            "bank": has_bank, "register": has_register,
            "payslips_emitted": payslips_emitted, "employees_true": n_emp,
        },
        "documents": documents,
        "truth": {
            "gross_total": gross_total,
            "employee_social_security_total": employee_social_security_total,
            "tax_withheld_total": tax_total,
            "employer_social_security_total": employer_social_security_total,
            "employer_cost_total": employer_cost_total,
            "net_total": net_total,
            "bank_net_total": bank_net,
            "employee_count": n_emp,
            "per_employee": employees,
        },
        "expected_validations": {"R1": r1, "R2": r2, "R3": r3, "R4": r4},
        "expected_figures": {
            "employer_cost_total": employer_cost_total,
            "bank_net_total": bank_net,
            "employee_count": n_emp,
        },
        "naive": naive,
    }


# Deterministic sample corpus: one case per edge case + canonical standards.
SAMPLE_PLAN = [
    ("case-0001", []),                    # standard, full close
    ("case-0002", ["bank_mismatch"]),     # R1 fails (bank +6% reconciliation break)
    ("case-0003", ["missing_register"]),  # no register -> R2/R4 legitimately skip
    ("case-0004", ["missing_payslip"]),   # register N, payslips N-1: R1 and R4 both catch it
    ("case-0005", ["missing_bank"]),      # bank->payslip fallback; R1 skips
    ("case-0006", ["single_employee"]),   # smallest valid close
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/sample", help="output dir (relative to eval/)")
    ap.add_argument("--n", type=int, default=0, help="random cases (0 = use sample plan)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pdf", action="store_true", help="also render PDFs (needs reportlab)")
    args = ap.parse_args()

    eval_dir = Path(__file__).parent
    out_dir = eval_dir / args.out
    rng = random.Random(args.seed)

    manifest = {"seed": args.seed, "cases": []}
    if args.n == 0:
        plan = SAMPLE_PLAN
    else:
        edge_pool = [[], [], ["bank_mismatch"], ["missing_payslip"],
                     ["missing_bank"], ["missing_register"], ["single_employee"]]
        plan = [(f"case-{i + 1:04d}", rng.choice(edge_pool)) for i in range(args.n)]

    for case_id, edges in plan:
        case = build_case(case_id, rng, edges)
        cdir = out_dir / case_id
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "ground_truth.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["cases"].append({"case_id": case_id, "edge_cases": edges})
        if args.pdf:
            _render_pdfs(cdir / "docs", case)
        print(f"  + {case_id}  edges={edges or ['standard']}  docs={len(case['documents'])}")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {len(plan)} cases -> {out_dir}/")


def _render_pdfs(docs_dir: Path, case: dict) -> None:
    """Render each labelled document to a minimal PDF for the live-extraction slot."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    docs_dir.mkdir(parents=True, exist_ok=True)
    W, H = A4
    truth = case["truth"]
    for d in case["documents"]:
        c = canvas.Canvas(str(docs_dir / d["source_file"]), pagesize=A4)

        def line(y, s, size=10, bold=False):
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            c.drawString(2 * cm, H - y * cm, s)

        line(2, case["company"], 14, bold=True)
        line(2.9, f"Period: {case['period']}   Issue: {d['issue_date']}")
        if d["doc_type"] == "bank_confirmation":
            line(4.2, "ZENITH BANK - BATCH PAYROLL TRANSFER", 12, bold=True)
            line(6, f"TOTAL TRANSFER (net): EUR {d['total_amount']:.2f}", 12, bold=True)
        elif d["doc_type"] == "payroll_register":
            line(4.2, "PAYROLL REGISTER (EMPLOYER SOCIAL SECURITY)", 12, bold=True)
            line(5.4, f"Gross total:              EUR {truth['gross_total']:.2f}")
            line(6.0, f"Employee social security: EUR {truth['employee_social_security_total']:.2f}")
            line(6.6, f"Employer social security: EUR {truth['employer_social_security_total']:.2f}")
            line(7.2, f"Net total:                EUR {truth['net_total']:.2f}")
            line(8.0, f"EMPLOYER COST TOTAL: EUR {truth['employer_cost_total']:.2f}", 11, bold=True)
            line(8.8, f"Employees: {truth['employee_count']}")
        else:  # payslip
            line(4.2, "PAYSLIP", 12, bold=True)
            line(5.4, f"Employee: {d.get('employee_name', '')} ({d.get('employee_code', '')})")
            line(6.6, f"NET PAY: EUR {d['total_amount']:.2f}", 12, bold=True)
        c.save()


if __name__ == "__main__":
    main()
