# Archon Article Replacement Figures

Use these figures with `demo/blog-post.md`.

| File | Purpose | Suggested alt text |
|---|---|---|
| `fig-1-architecture.svg` | Live Nebius AI Jobs dispatch architecture | Revision r133 runs the FastAPI orchestrator with the Nebius Jobs backend, explicit project-local routes, and inline only as an emergency fallback |
| `fig-2-control-loop.svg` | Primary product-control figure | Successfully extracted documents receive document-type refinement and event linking; review confirms company ownership; the approved set then enters expense categorization, deterministic analysis, and controls; failed-file UI surfacing remains open |
| `fig-3-pipeline.svg` | Workflow and dispatch control plane | The live r133 Endpoint dispatches extraction and analysis AI Jobs around the human-review gate; inline remains emergency-only |
| `fig-4-cost-model.svg` | Resource-placement and cost-evidence model | Always-on CPU orchestration, on-demand CPU Jobs, and managed GPU inference, with measured Job runtime and cost still unclaimed |
| `fig-2-payroll-gap.svg` | Optional payroll-event explainer | Bank confirmation, payroll register, and payslips linked as complementary evidence for cash, management expense, and named checks |

The article should use `fig-2-control-loop`, not the older payroll-only framing, as its second primary figure. Solid paths in the updated figures show the live r133 Jobs-mode configuration. Dashed inline paths are operator-selected emergency fallback only. Deployment success is established; completed application extraction or analysis Job execution is not yet claimed.

The SVGs are self-contained. The matching PNGs in `png/` are rendered at 1600px width for Medium and other platforms that reject SVG.
