"""Load a labelled corpus (directory of `<case>/ground_truth.json`)."""

from __future__ import annotations

import json
from pathlib import Path


def load_corpus(corpus_dir: str | Path) -> list[dict]:
    """Return the list of ground-truth case dicts, sorted by case_id."""
    cdir = Path(corpus_dir)
    if not cdir.is_absolute():
        # allow paths relative to the eval/ package or the repo
        here = Path(__file__).resolve().parents[1]
        for base in (Path.cwd(), here, here.parent):
            if (base / cdir).exists():
                cdir = base / cdir
                break
    cases = []
    for gt in sorted(cdir.glob("*/ground_truth.json")):
        cases.append(json.loads(gt.read_text(encoding="utf-8")))
    if not cases:
        raise FileNotFoundError(f"No ground_truth.json found under {cdir}")
    return cases
