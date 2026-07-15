#!/usr/bin/env python3
"""Compatibility entry point for the final Challenge article PDF.

The maintained builder lives in ``scripts/build_submission_pdf.py`` and uses
ReportLab plus the current article figures.  Keep this wrapper so the command
documented in older revisions continues to work without recreating the stale
pre-correction PDF.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "build_submission_pdf.py"

if __name__ == "__main__":
    sys.argv = [str(BUILDER), "--sync-demo"]
    runpy.run_path(str(BUILDER), run_name="__main__")
