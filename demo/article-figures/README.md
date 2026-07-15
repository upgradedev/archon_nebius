# Archon Article Replacement Figures

Use these figures with `demo/blog-post.md`.

| File | Purpose | Suggested alt text |
|---|---|---|
| `fig-1-architecture.svg` | Deployed architecture and designed Jobs path | Archon live inline CPU Endpoint path and separately marked Nebius AI Jobs target architecture |
| `fig-2-control-loop.svg` | Primary product-control figure | Successfully extracted documents receive document-type refinement and event linking; review confirms company ownership; the approved set then enters expense categorization, deterministic analysis, and controls; failed-file UI surfacing remains open |
| `fig-3-pipeline.svg` | Workflow and execution modes | Archon workflow using live inline Endpoint subprocesses, with the unexecuted AI Jobs design clearly separated |
| `fig-4-cost-model.svg` | Resource-placement model | Current CPU Endpoint fallback and designed on-demand CPU Jobs both call the Nebius Inference API, with no application GPU |
| `fig-2-payroll-gap.svg` | Optional payroll-event explainer | Bank confirmation, payroll register, and payslips linked as complementary evidence for cash, management expense, and named checks |

The article should use `fig-2-control-loop`, not the older payroll-only framing, as its second primary figure. Solid execution paths mean observed live deployment; dashed paths mean implemented design that was not executed because the tenant has zero CPU AI-Jobs quota.

The SVGs are self-contained. The matching PNGs in `png/` are rendered at 1600px width for Medium and other platforms that reject SVG.
