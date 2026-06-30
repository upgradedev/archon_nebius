"""
Load the REAL Archon pipeline agents so the harness scores production code, not
a re-implementation.

The extraction pipeline (`jobs/extraction`) and the analysis pipeline
(`endpoints/analysis`) each ship their own top-level `models` package. Importing
both in one process collides on the `models` name, so each pipeline is loaded in
isolation: insert its root on `sys.path`, purge any prior `models`/agent
modules, import, then restore.

Agent modules are loaded **by file path** (not `import_module("agents.x")`) so
the package `__init__` is never executed — the analysis `agents/__init__.py`
eagerly imports `narrator` -> `openai`, which the offline harness does not (and
should not) require. The agents we load import only `models.*` (absolute) +
stdlib, so flat-name file loading is safe and dependency-light (just `pydantic`).
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXTRACTION_ROOT = REPO / "jobs" / "extraction"
ANALYSIS_ROOT = REPO / "endpoints" / "analysis"

_AGENT_FLAT = {"classifier", "event_linker", "validator", "pnl_agent"}


def _purge() -> None:
    for key in list(sys.modules):
        if key == "models" or key.startswith("models.") or \
           key == "agents" or key.startswith("agents.") or key in _AGENT_FLAT:
            del sys.modules[key]


def _load(root: Path, model_modules: list[str], agent_files: dict[str, str]) -> dict:
    _purge()
    sys.path.insert(0, str(root))
    try:
        out = {m: importlib.import_module(m) for m in model_modules}
        for key, relpath in agent_files.items():
            flat = key.rsplit(".", 1)[-1]
            spec = importlib.util.spec_from_file_location(flat, str(root / relpath))
            module = importlib.util.module_from_spec(spec)
            sys.modules[flat] = module          # so internal imports resolve
            spec.loader.exec_module(module)
            out[key] = module
        return out
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass


def load_extraction() -> dict:
    """Return the real extraction models + classifier/event_linker/validator."""
    return _load(
        EXTRACTION_ROOT,
        ["models.document", "models.event", "models.validation"],
        {
            "agents.classifier": "agents/classifier.py",
            "agents.event_linker": "agents/event_linker.py",
            "agents.validator": "agents/validator.py",
        },
    )


def load_analysis() -> dict:
    """Return the real analysis model + P&L agent (purges extraction modules)."""
    return _load(
        ANALYSIS_ROOT,
        ["models.financial"],
        {"agents.pnl_agent": "agents/pnl_agent.py"},
    )
