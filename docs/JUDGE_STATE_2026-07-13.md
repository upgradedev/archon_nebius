# Judge State — Archon on Nebius — 2026-07-13

> Single source of truth for any agent/AI opening this repo: where this build stands against the
> Nebius Serverless AI Builders Challenge rubric, what was harmonized in the 2026-07-12/13 session, and
> the ranked path to **exceed the target bar (> 9.5 / 10)**. Derived from the workspace judgment review
> (`JUDGMENT_REVIEW_2026-07-12.md` + `BUILD_AUDIT_2026-07-12.md`), re-verified against this repo on 2026-07-13.
>
> Video and blog are treated as **done / ready-to-submit** and are deliberately excluded from the path below.

## Challenge + target

| | |
|---|---|
| Challenge | Nebius Serverless AI Builders Challenge |
| Deadline | **2026-07-15** (1 shot per Tenant ID via Nebius Academy) |
| Rubric | 6 **equal** criteria; tiebreaker = reproducibility, then community engagement |
| Target bar to exceed | **> 9.5 / 10** |
| Current judged score | **~8.5 / 10** (was ~8.0–8.2 pre-harmony; lifted by merged PRs #122–#127) |

## Current judge score — per criterion (6 equal)

| Criterion | Score | Notes |
|---|---|---|
| Technical implementation | 9 | 4-agent extraction Job + 7-agent analysis Job; 327 backend/pipeline + 36 e2e offline tests; ADR-009 capacity-probe failover; KMS envelope encryption. |
| Reproducibility (tiebreaker) | 8.5 | `docker compose up` + `scripts/test-pipeline.sh` + `scripts/demo-failover.sh`; README quickstart with runtime expectations. Gap: no recorded one-command demo GIF/asciinema. |
| Educational content | 7.5 | Blog ready to publish (harmonized to measured 72% / EUR 133,381 / 37-37); README deep-dives on injection fence + capacity probe. Weakest criterion until the blog is *published*. |
| Product-usage depth | 9 | Nebius AI Jobs (×2: extraction + analysis) + CPU AI Endpoint + Object Storage + Managed PostgreSQL + Inference API + KMS = 6 primitives, cited in README to code. |
| Real-world usefulness | 8.5 | Measured ~72% payroll-cost understatement / ~35% employer wedge (`eval/BASELINE.md`); universal financial-intelligence framing. |
| Originality | 8.5 | Three under-illuminated points now surfaced in README: capacity-probe failover (ADR-009), ReconciliationAgent, prompt-injection fence + deterministic scan. |

## Discrepancies fixed this session (merged PRs)

- **#127** — blue/green endpoint deploy: never reuse a wedged endpoint name (fixes the 502/stale-endpoint live-surface risk).
- **#126** — re-rendered synced demo video (5:20) + narration trimmed to the beat timeline.
- **#125** — judgment-review harmony across demo assets + blog: measured **72%** / **EUR 133,381** / **37-37** validation rules (superseded the stale 28% / 96.88% / dormant-rules figures).
- **#124** — consistency sweep: truthful DB tables, correct test counts, corrected agent order (Validator before Employee), corrected `POST /analyze` output shape (returns a job id, not a `FinancialReport`).
- **#123** — README foregrounds measured impact and cites Nebius primitives in code.
- **#122** — keep-warm workflow now asserts HTTP 200 (was false-green, likely why the endpoint sat cold) + README test count corrected.

**Already resolved / verified in-repo (do not re-list as pending):** ADR-009 file exists at
`docs/adr/ADR-009-capacity-probe-failover.md` and is referenced from README; the injection fence and the
deterministic `jobs/extraction/injection_scan.py` are documented in README; ReconciliationAgent
(`jobs/analysis/agents/reconciliation_agent.py`) is in the diagram and the fusion narrative.

## Path to exceed the target (> 9.5) — ranked

> Video + blog publication excluded (done / ready-to-submit). Ordered by score leverage against the rubric.

1. **[USER] Verify the signed-in E2E works live** — log in at https://archon-pnl.web.app, upload
   `sample-data/generated/`, confirm a report renders end-to-end. This is the single highest-value evidence
   for *real-world usefulness* + *product-usage depth* (proves the deployed Endpoint + Jobs + storage + DB
   chain, not just the local stack). Endpoint is LIVE after the blue/green fix (#127).
2. **[USER] Keep the endpoint warm through judging** — confirm `cpu-d3` AI-Jobs quota > 0 and leave the
   Endpoint warm so a judge hitting `/api/health` sees 200, not a cold-start 502. (Tiebreaker = reproducibility;
   a judge who can reach the live demo scores it, one who can't doesn't.)
3. **[CODE] Record a one-command reproducibility demo (GIF / asciinema)** — the scripts already exist
   (`scripts/test-pipeline.sh`, `scripts/demo-failover.sh`); capturing a terminal recording embedded in the
   README turns "reproducible in principle" into "reproducible on sight" and directly lifts the tiebreaker
   criterion. Optionally wrap the smoke path in a single `make verify` target.
4. **[CODE] Add a short "Nebius primitive → where used → test that proves it" table to the README** — the
   primitives are already cited inline; a single scannable table makes *product-usage depth* legible to a
   fast-reading judge (6 primitives is the strongest axis; make it impossible to miss).
5. **[CODE] Cross-link the three originality points into a single "What's novel here" README section** — they
   exist but are spread across the doc (line 36 framing, 127 fusion, 133 fence, 324 ADR-009). One anchored
   section consolidates the *originality* case.

## Verified-harmonized (no action needed)

- Analysis pipeline is a **Job** (not an Endpoint) everywhere — diagram, agent table, deploy scripts.
- Agent order Validator-before-Employee is consistent across README, code, and diagram.
- Measured figures are uniform: **~72%** full understatement / **~35%** employer wedge / **EUR 133,381** /
  37-of-37 validation rules.
- Nebius primitives table and the €133k worked example are present and truthful.
