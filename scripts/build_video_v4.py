#!/usr/bin/env python3
"""Build the corrected v4 Archon/Nebius technical presentation.

This version keeps every claim inside the boundary demonstrated by the repo:
failed-file metadata is recorded but not surfaced in the current review UI,
supplier reconciliation is unit-tested but not wired to extraction, and the
live Endpoint uses the inline subprocess runner because CPU AI-Jobs quota is 0.
"""

from __future__ import annotations

import asyncio

import build_video_v3 as base


SLIDES = [
    {
        "title": "Archon",
        "subtitle": "Financial-document control on Nebius Serverless AI",
        "kind": "questions",
        "items": [
            ("What is this?", "Structured extraction and document-type classification"),
            ("Where does it belong?", "Company-profile check and human review"),
            ("What belongs together?", "A bounded payroll-event linking example"),
            ("What can we prove?", "Named validations with source-file references"),
        ],
        "narration": (
            "Small-business finance starts with documents that must be understood, classified, reviewed, "
            "and connected before anyone should trust a period view. Archon is a financial-document control "
            "prototype built around that workflow. It extracts structured records, lets a person decide what "
            "proceeds, links one implemented event family, and reports bounded validation findings. It is not "
            "automated entry, clear categorization, human review, and bounded cross-document controls. Accounting "
            "journals and general payment matching remain beyond this prototype."
        ),
    },
    {
        "title": "Extraction first; review before analysis",
        "subtitle": "The actual order in the current implementation",
        "kind": "flow",
        "items": [
            ("1. Extract", "PDF · DOCX · scan · image"),
            ("2. Classify", "structured fields · type refinement"),
            ("3. Link + validate", "payroll events · R1–R4 before review"),
            ("4. Review", "successful docs · correct · exclude"),
            ("5. Analyze", "approved period set"),
        ],
        "footer": (
            "Failed-file metadata is recorded by extraction; the current review UI does not display it."
        ),
        "narration": (
            "The extraction package runs before the human review gate. It extracts, classifies, links payroll "
            "documents, applies R one through R four, and writes documents, events, validations, and a machine-"
            "readable failed-file summary to Object Storage. The current review screen loads only documents "
            "that extracted successfully, so failed files are recorded in extraction artifacts and logs, but "
            "are not yet visible in that interface. The reviewer can correct a type or exclude a record. The "
            "approved documents then replace the period document set, and analysis reads that reviewed set."
        ),
    },
    {
        "title": "Payroll is one bounded linking example",
        "subtitle": "Validation traceability — not proof that every liability was paid",
        "kind": "payroll",
        "items": [
            ("Bank confirmation", "Net transfer · document date"),
            ("Payroll register", "Gross pay · employer cost · headcount"),
            ("Payslips", "Employee-level net amounts"),
            ("R1–R4 validations", "Amount · ratio · date · headcount · source files"),
        ],
        "narration": (
            "Payroll demonstrates the implemented event-linking pattern. The extraction Event Linker groups a "
            "bank confirmation, payroll register, and payslips by company and document month. Four deterministic "
            "checks compare bank and payslip totals, an employer-cost ratio, the bank document date, and headcount. "
            "Validation findings carry the relevant source-file names, which is the traceability implemented today. "
            "These checks do not verify that payroll taxes or social-security liabilities were remitted, and they do "
            "not establish general report-wide lineage for every displayed number."
        ),
    },
    {
        "title": "Supplier reconciliation — exact boundary",
        "subtitle": "A unit-tested analysis component that is not wired to extraction",
        "kind": "boundary",
        "items": [
            ("IMPLEMENTED", "Agent compares pre-structured statement entries\nwith recorded invoice numbers and totals"),
            ("NOT WIRED", "Current extractors do not produce\nstatement entries or statement balances"),
            ("NEXT", "Wire statement extraction\nThen add invoice ↔ payment or collection\nand remittance event families"),
        ],
        "narration": (
            "The repository includes a unit-tested supplier Reconciliation Agent. When it receives pre-structured "
            "statement entries, it can identify invoice numbers missing from the uploaded set, unmatched uploads, "
            "and a balance difference. The current image, PDF, and DOCX extraction mappings do not populate those "
            "statement entries, so this component is not an end-to-end user flow in the submitted build. It is also "
            "not a bank-payment matcher. Invoice settlement, collections, duplicates, wrong-vendor payments, and "
            "tax or contribution remittances remain future event families."
        ),
    },
    {
        "title": "The deployed Nebius architecture",
        "subtitle": "Job design, live inline execution, and exact image registries",
        "kind": "architecture",
        "items": [
            ("CPU AI Endpoint", "FastAPI orchestration · live inline runner"),
            ("Extraction pipeline", "AI Job design · subprocess in live Endpoint"),
            ("Analysis pipeline", "AI Job design · subprocess in live Endpoint"),
            ("Inference API", "Qwen2.5-VL extraction · Llama 3.3 narration"),
            ("Artifacts & images", "Object Storage authority · PostgreSQL mirror\nNebius Registry: job images · GHCR: Endpoint image"),
        ],
        "narration": (
            "A Nebius CPU AI Endpoint hosts the FastAPI backend. Extraction and analysis are packaged as separate "
            "on-demand AI Job entry points, but this tenant currently has zero CPU Jobs quota. The live Endpoint "
            "therefore runs those same packages as isolated subprocesses. Qwen two-point-five V L performs document "
            "extraction and Llama three-point-three produces optional narration through the Nebius Inference API. "
            "Object Storage is authoritative for raw, extracted, and report artifacts; Managed PostgreSQL is a best-"
            "effort relational mirror. Nebius Container Registry hosts the two job images, while the live Endpoint "
            "image is pulled from GitHub Container Registry. Firebase supplies the authenticated browser edge."
        ),
    },
    {
        "title": "Two pipelines separated by review",
        "subtitle": "Analysis does not consume the pre-review event artifact directly",
        "kind": "proof",
        "items": [
            ("EXTRACTION · BEFORE REVIEW", "Extract → deterministic type refinement → payroll link → R1–R4 → Object Storage artifacts"),
            ("REVIEW BOUNDARY", "Load successfully extracted documents → correct or exclude → persist the approved period document set"),
            ("ANALYSIS · AFTER REVIEW", "Read reviewed documents → reclassify → compute period views → revalidate → optionally narrate"),
        ],
        "footer": "Language models read and narrate; Python performs arithmetic and named validations.",
        "narration": (
            "The extraction and analysis packages are separated by the review boundary. Extraction creates an event "
            "and validation artifact from the successful pre-review documents. The browser then sends back the "
            "approved period set. Analysis loads those reviewed documents, performs its own classification, builds "
            "the current P and L and cash-flow views, re-runs the payroll validations, builds employee summaries, "
            "calls the supplier component when structured inputs exist, and finally requests narration. The language "
            "models operate at the unstructured edges. Python performs the arithmetic and controls, and a narration "
            "failure falls back to a deterministic summary."
        ),
    },
    {
        "title": "What the evaluation actually proves",
        "subtitle": "Downstream ceiling and sensitivity — no published live-Qwen score",
        "kind": "evaluation",
        "items": [
            ("Classification", "100.00%", "74.29%"),
            ("Selected fields", "100.00%", "77.62%"),
            ("Payroll fusion", "100.00%", "54.05%"),
            ("Rules repaired", "0 / 37", "37 / 37"),
        ],
        "narration": (
            "The offline evaluation harness imports the real downstream agents and scores forty labelled synthetic "
            "payroll cases. With deterministic perfect structured input, classification, selected-field, validation, "
            "and payroll-fusion accuracy reach one hundred percent. A deliberately degraded extractor drops "
            "classification to seventy-four point two-nine percent, selected fields to seventy-seven point six-two, "
            "validation outcomes to sixty-six point eight-seven, and fusion to fifty-four point zero-five. The harness "
            "also moved two formerly dormant rules from zero of thirty-seven to thirty-seven of thirty-seven applicable "
            "cases. The one-hundred-percent result is a downstream ceiling, not a live Qwen vision score; no live-"
            "extraction accuracy result is published in this submission."
        ),
    },
    {
        "title": "Exact AI Jobs failover behavior",
        "subtitle": "The live path is inline because CPU AI-Jobs quota is zero",
        "kind": "operations",
        "items": [
            ("1", "Create rejected for quota or capacity", "Try the next configured project and preset"),
            ("2", "Terminal or vanished with zero instances", "Clean up the never-provisioned job; then advance"),
            ("3", "Still pending when the probe ends", "Keep the same job and poll it; never fail over by elapsed time"),
            ("4", "Application reached compute and failed", "Surface the application error; do not retry another preset"),
        ],
        "narration": (
            "The failover rule is narrower than a timeout. If job creation is rejected for quota or capacity, Archon "
            "tries the next configured project and preset. If a job reaches a terminal failure with zero instances, "
            "or vanishes while provisioning, Archon cleans up that never-provisioned job and advances. If the bounded "
            "probe ends while the job is still pending, it keeps that same job and continues polling; elapsed time alone "
            "never triggers failover or a duplicate submission. If compute was provisioned and the application then "
            "fails, Archon surfaces the application error without retrying another preset. This logic is built and "
            "tested, but the current live product uses the inline subprocess path because tenant CPU Jobs quota is zero."
        ),
    },
    {
        "title": "Public deployment evidence",
        "subtitle": "Running Nebius Endpoint and state checks — not a successful AI Job claim",
        "kind": "proof",
        "items": [
            ("DEPLOYMENT · 15 JULY 2026", "Nebius CPU Endpoint reached RUNNING with JOB_RUNNER_BACKEND=inline"),
            ("LIVE CHECKS", "PostgreSQL /health/db reported reachable · Firebase BFF /api/health returned HTTP 200"),
            ("PUBLIC ACTIONS LOGS", "Deploy: github.com/upgradedev/archon_nebius/actions/runs/29419841856\nPG seed: github.com/upgradedev/archon_nebius/actions/runs/29309815367"),
        ],
        "footer": "Deployment evidence ≠ CPU AI Job execution; no Job provisioned under the zero-quota tenant.",
        "narration": (
            "The deployment evidence is public. GitHub Actions run twenty-nine billion four hundred nineteen million "
            "eight hundred forty-one thousand eight hundred fifty-six shows the Nebius CPU Endpoint reaching running "
            "state with the inline runner, PostgreSQL reachable through its private endpoint, and the Firebase B F F "
            "health route returning H T T P two hundred. A separate public seed run exercises authenticated report "
            "serving and triggers the PostgreSQL read-model mirror. These logs prove the deployed Endpoint and state "
            "path. They do not claim that a CPU AI Job provisioned; none did under the tenant's zero Jobs quota."
        ),
    },
    {
        "title": "Current proof and explicit next work",
        "subtitle": "A controlled-record prototype with bounded, reproducible claims",
        "kind": "close",
        "items": [
            ("TODAY", "Mixed-file extraction · type refinement\nhuman review of successful documents\npayroll R1–R4 · validation source files\nlive inline execution on a Nebius Endpoint"),
            ("NEXT", "Show failed-file summaries in the review UI\nwire supplier-statement extraction\ninvoice ↔ payment or collection · remittances\njournal export and accounting integrations"),
        ],
        "narration": (
            "The submitted proof is deliberately bounded: mixed-file extraction, structured records, deterministic "
            "type refinement, human review of successfully extracted documents, payroll linking, four named checks "
            "with source-file references, reproducible downstream evaluation, and a live Nebius Endpoint using the "
            "inline fallback. The next work is equally explicit: surface failed-file summaries in the review interface, "
            "wire supplier-statement extraction, add invoice-to-payment and invoice-to-collection events, verify tax "
            "and contribution remittances, and integrate with accounting journals. That boundary is the honest Archon "
            "story for this challenge."
        ),
    },
]


def main() -> None:
    base.SLIDES = SLIDES
    base.WORK = base.ROOT / "demo" / "video-v4-work"
    base.OUT = base.ROOT / "demo" / "archon-nebius-presentation-v4.mp4"
    asyncio.run(base.main())


if __name__ == "__main__":
    main()
