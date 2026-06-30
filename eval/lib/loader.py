"""
Load the REAL Archon pipeline agents so the harness scores production code, not
a re-implementation.

The extraction pipeline (`jobs/extraction`) and the analysis pipeline
(`endpoints/analysis`) each ship their own top-level `models` package. Importing
both in one process collides on the `models` name, so we import each pipeline in
isolation: insert its root on `sys.path`, purge any prior `models`/`agents`
modules, import, then restore. The agents we load import only `models` +
stdlib — no `openai`/network — so this is dependency-light and offline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXTRACTION_ROOT = REPO / "jobs" / "extraction"
ANALYSIS_ROOT = REPO / "endpoints" / "analysis"


def _purge() -> None:
    for key in list(sys.modules):
        if key == "models" or key.startswith("models.") or \
           key == "agents" or key.startswith("agents."):
            del sys.modules[key]


def _load(root: Path, modules: list[str]) -> dict:
    _purge()
    sys.path.insert(0, str(root))
    try:
        return {m: importlib.import_module(m) for m in modules}
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass


def load_extraction() -> dict:
    """Return the real extraction models + classifier/event_linker/validator."""
    return _load(EXTRACTION_ROOT, [
        "models.document", "models.event", "models.validation",
        "agents.classifier", "agents.event_linker", "agents.validator",
    ])


def load_analysis() -> dict:
    """Return the real analysis model + P&L agent (purges extraction modules)."""
    return _load(ANALYSIS_ROOT, ["models.financial", "agents.pnl_agent"])
