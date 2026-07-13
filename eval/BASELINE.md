# Archon Evaluation Harness — Measured Baselines

This is the measurement frame that turns "it works" into a number. It scores the
**real** Archon pipeline agents — `ClassifierAgent`, `EventLinkerAgent`,
`ValidatorAgent`, `PnLAgent` (imported from `jobs/extraction/` and
`jobs/analysis/`, not re-implemented) — against a labelled synthetic corpus
of SMB payroll documents.

Reproduce (offline, no API key, only `pydantic`):

```bash
python eval/generate_corpus.py        # rewrite the committed JSON sample corpus
python eval/evaluate.py               # score the real agents -> table + RESULTS.json
python -m pytest eval/tests -q        # assert the baselines below stay true
```

Both corpora are committed as JSON labels only (no PDFs, no extra deps): the
6-case `eval/corpus/sample/` and the 40-case `eval/corpus/full/`. The committed
`eval/RESULTS_full.json` is the machine-readable output for the full corpus, so
the headline 40-case table below regenerates offline and byte-for-byte:

```bash
python eval/generate_corpus.py --out corpus/full --n 40 --seed 7
python eval/evaluate.py --corpus eval/corpus/full --out eval/RESULTS_full.json
```

Both generation and scoring are deterministic (`--seed 7`), so re-running the two
commands reproduces `RESULTS_full.json` and every full-corpus number in this file.

Runtime: ~3 s for the sample, ~6 s for the full corpus on a laptop CPU. Cost:
**€0** — the perfect/degraded extractors are deterministic; no inference is
called. (The optional live-extraction slot does call the Nebius Inference API —
see `LIVE_EXTRACTION.md`.)

---

## 1. What is measured

| Metric | Definition | Match rule |
|---|---|---|
| **Classification accuracy** | `doc_type` after the real `ClassifierAgent` vs the labelled type, per source file | exact |
| **Field accuracy** | every extracted number/date the current prompt emits (`total_amount`, `issue_date`) vs the label | numbers within 1 cent OR ≤0.5% relative; dates exact |
| **Fusion figure accuracy** | the payroll **expense the real `PnLAgent` reports** vs the independently-computed true employer cost | same numeric rule |
| **Validation-outcome accuracy** | the real `ValidatorAgent` R1–R4 pass/fail vs **domain truth** | exact boolean |
| **Rule activity** | of the cases where a rule *could* apply, how often it actually evaluated vs skipped | — |
| **Naive floor** | bank-only "payroll cost" vs the true employer cost | EUR + % |

The figure "expected" (the true totals) is kept **separate** from the validation
"expected" (is this payroll actually consistent?) so a validation bug cannot hide
behind a correct number.

The labels in each case's `documents[]` mirror **exactly the fields the current
production extraction prompt emits** (`jobs/extraction/extractors/image.py::
EXTRACTION_PROMPT`): generic document fields + `total_amount`, plus the payroll
fields the prompt now requests — `gross_pay_total`, `employer_cost_total`,
`net_pay_total`, `employee_count` on the register and `net_pay_total` on the bank
confirmation. So the "perfect" extractor is the real product's ceiling — it is
faithful to what the deployed pipeline can actually know, not to an idealised
schema. The full payroll truth (gross, social security, per-employee) lives in
`truth{}` and feeds the naive floor and the domain-truth validations.

---

## 2. Measured baselines

### Perfect-extraction CEILING

Perfect read of the fields the current prompt emits → the **real**
`ClassifierAgent` / `EventLinkerAgent` / `ValidatorAgent` / `PnLAgent`.

| Metric | Sample (6) | Full (40) |
|---|---|---|
| Classification accuracy | **100.00%** | **100.00%** |
| Field accuracy | **100.00%** | **100.00%** |
| Fusion figure accuracy | **100.00%** | **100.00%** |
| Validation-outcome accuracy | **100.00%** (24/24) | **100.00%** (160/160) |

The fusion result is the load-bearing positive: under perfect extraction the
`PnLAgent` reports the **employer cost** (gross + employer social-security), not
the bank net transfer, to the cent across 40 diverse cases — the core "the bank transfer alone is only the net-wages component" thesis is verified, not asserted.

Validation-outcome is now **100%** — perfect extraction reproduces domain truth
on all four rules. It used to sit at 95.83% / 96.88% because R4 was dormant and
missed the `missing_payslip` cases; activating R2/R4 (below) closed that gap.

### Rule activity at the ceiling (all four rules now live)

| Rule | Checks | Fired / applicable (full) | State |
|---|---|---|---|
| **R1** | bank net ≈ Σ payslip nets (±2%) | 31 / 31 | **active** |
| **R2** | employer-cost / net ratio band | 37 / 37 | **active** |
| **R3** | payment date ≤ period end | 31 / 31 | **active** |
| **R4** | register headcount == payslips | 37 / 37 | **active** |

**R2 and R4 now fire on every applicable case.** They read
`register.employer_cost_total`, `register.net_pay_total`, and
`register.employee_count` — fields the extractor now populates: the prompt
requests them (`image.py::EXTRACTION_PROMPT`) and `image.py` / `pdf.py` /
`docx.py` map them onto `ExtractedDocument`. This was the keystone finding of the
first version of this harness — *"the fields R2/R4 need are read in four places
but written in none, so 0/37 firings"* — and this change resolves it: the same
number moves from **0/37 to 37/37**, measured, not asserted. (Two supporting
fixes rode along: the R2 ratio band was recalibrated from the structurally-wrong
`[1.25, 1.45]` to `[1.40, 2.60]` — see §3 F2 — and the degraded extractor gained
a structural net-line error so R2 is stress-tested, not merely switched on.)

### Sensitivity check (the metrics actually move)

A deliberately weak extractor (±6% numeric noise on the totals incl.
`employer_cost_total`, a structural net-line misread on the register, and a
generic `doc_type` on half the payroll docs — some recoverable by the
`ClassifierAgent`, some not) scores well below the ceiling:

| Metric | Ceiling | Degraded (sample) | Degraded (full) |
|---|---|---|---|
| Classification | 100.00% | 77.14% | 74.29% |
| Field | 100.00% | 77.14% | 77.62% |
| Fusion figure | 100.00% | 20.00% | 54.05% |
| Validation-outcome | 100.00% | 66.67% | 66.87% |

Fusion accuracy collapses far faster than field accuracy — small per-field
extraction errors compound through the fusion sums. Validation-outcome also
falls sharply (66.87% full): the degraded extractor's structural net-line
misread pushes the employer-cost/net ratio out of R2's band, so **R2 fires and
flags the corrupted extraction** — exactly the failure mode R2 exists for. That
is the signal a real extractor should be optimised against, and it confirms both
that the classifier earns its place (it recovers a chunk of the
misclassified-as-generic docs) and that R2 catches a defect the perfect
extractor never produces.

### Naive-bookkeeping FLOOR — reconciliation measured on the sample

These are measurement figures on the synthetic corpus, not a customer result. The owner who books the bank salary transfer as "the payroll cost":

| Quantity | Sample (5 bank cases) | Full (31 bank cases) |
|---|---|---|
| Total bank-only (the wrong number) | EUR 36,355.30 | EUR 185,543.72 |
| Total true employer cost | EUR 62,503.72 | EUR 318,925.43 |
| **Total reconciled beyond bank net** | **EUR 26,148.42** | **EUR 133,381.71** |
| Mean reconciled amount, % of true cost | 41.37% | 41.84% |
| Mean reconciled amount, % over bank net | 70.65% | 71.97% |
| Mean employer social-security wedge, % over bank | 35.22% | 35.49% |

**Two numbers, reported separately on purpose.** The **~35%** figure is the
*employer social-security wedge only* (employer social-security ÷ bank net) —
what the register adds on top of the transfer purely from the employer's own
contribution. The **~72%** figure is the *full* reconciliation delta (true employer
cost ÷ bank net − 1): it also folds in the withheld employee social-security and
income tax the bank transfer nets out, so it is roughly double. Both are honest
and measured from `truth{}`; they answer different questions, and every
Archon-facing surface should say which one it means. (This measured split
supersedes the older "~28%" copy that predated the current corpus rates; that
number matched neither ratio and has been retired — see the repo-wide unification
in the docs.)

---

## 3. Findings the harness surfaced (under perfect inputs)

These appear with *perfect* extraction — perfect inputs, pipeline output vs
domain truth. They are real, not OCR artefacts. F1 and F2 were the harness's
original keystone findings; this change **resolves both** — kept here as a
before/after record because the resolution is the whole point of the harness.

### F1 (RESOLVED) — R2 and R4 were dormant because the fields they need were never extracted

The single biggest finding of the first harness version.
`register.employer_cost_total`, `net_pay_total`, and `employee_count` were read
by the validator and the P&L / employee agents but populated by no extractor, so
R2/R4 skipped on every case (0/37). Concretely, the `missing_payslip` cases
(register reports N, only N-1 payslips on file) are a genuine inconsistency:
**R1 caught them** (bank net ≠ Σ payslip nets), but **R4 could not** — it
skipped, so the harness recorded an R4 divergence on every such case
(`case-0004` in the sample; 5 cases in the full corpus).

**Fix applied (this change):** the payroll fields were added to
`EXTRACTION_PROMPT` and mapped in `image.py` / `pdf.py` / `docx.py`. The harness
is the before/after: R2/R4 move from **0/37 to 37/37** firings, the R4
divergences disappear, and validation-outcome rises 96.88% → **100%** at the
ceiling. R4 now catches the `missing_payslip` close it used to miss.

### F2 (RESOLVED) — the R2 ratio band was too low for a full-cost payroll

The old band checked `employer_cost / net ∈ [1.25, 1.45]`. In any payroll where
the employer's social charges and the employee's withholdings are a material
fraction of gross, the ratio is structurally higher — on this corpus ~1.73
(employer cost ≈ 1.26 × gross; net ≈ 0.73 × gross) — so simply switching R2 on
with the old band would have *failed* a perfectly consistent payroll. The band
was therefore **recalibrated to `[1.40, 2.60]`**, derived from payroll structure
(employer cost 1.20–1.35 × gross; net 0.55–0.82 × gross → ratio ≈ 1.46–2.45,
widened for headroom — see `jobs/extraction/agents/validator.py`), not fitted to
the sample. The consistent corpus ratio 1.73 sits inside; the degraded
extractor's structural net-line misread (~1.26) sits below and is flagged — so
R2 now both passes a real payroll *and* catches a real extraction defect, rather
than moving from a dormant rule into a mis-calibrated one.

### F3 (note) — the event linker buckets by `issue_date`, so a late cross-month payment splits the event

`EventLinkerAgent` groups documents by `(company, YYYY-MM-from-issue_date)`. A
bank confirmation paid in the *following* month lands in a different period
bucket from its register/payslips, so R3 (payment-date check) never sees both in
one event and cannot flag the lateness. Noted, not scored (the corpus avoids
this confound); it is a linker-keying limitation worth a follow-up.

### F4 (note) — classifier keyword matching is ASCII-only

`ClassifierAgent._search_text` strips non-ASCII (`encode("ascii","ignore")`)
before matching, but several keyword sets are raw non-Latin script — those
entries can never match. Recovery works through the ASCII/English keywords (`payroll
register`, `social security`, `payslip`, `payroll transfer`, …). The corpus
text uses those, mirroring how the deployed classifier actually behaves.

---

## 4. Where the live-extraction layer plugs in

The harness is parameterised on one function shape
(`extractor(ext_modules, case) -> list[ExtractedDocument]`):

- `perfect_extractor` — returns the current prompt's fields (the ceiling above).
- `degraded_extractor` — perturbs them (the sensitivity check).
- **live slot** — read each case's rendered `docs/*.pdf` with Qwen2.5-VL on the
  Nebius Inference API and return `ExtractedDocument[]`. See `LIVE_EXTRACTION.md`.

Drop a real extractor in and the same four metrics score its classification,
field, and end-to-end fusion accuracy against the same ground truth, with no
other change.
