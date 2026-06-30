"""
Live-extraction accuracy — score the REAL production extractor (Qwen2.5-VL on the
Nebius Inference API) against the harness ground truth.

This is the open slot from BASELINE.md §4: instead of the deterministic
perfect/degraded reference extractors, it runs `jobs/extraction`'s real
`PdfExtractor` over each case's rendered PDFs and feeds the result through the
same four metrics. It is the honest "does real extraction work" number — not the
perfect-extraction ceiling (100% by construction).

Requirements (NOT needed for the offline harness):
  * rendered PDFs:   python eval/generate_corpus.py --pdf
  * extractor deps:  pip install -r jobs/extraction/requirements.txt
  * credentials:     NEBIUS_INFERENCE_BASE_URL, NEBIUS_INFERENCE_API_KEY [, VISION_MODEL]

Usage:
    python eval/live_extract.py eval/corpus/sample
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.corpus import load_corpus     # noqa: E402
from lib import metrics, loader        # noqa: E402


def main() -> None:
    if not os.getenv("NEBIUS_INFERENCE_API_KEY"):
        sys.exit("NEBIUS_INFERENCE_API_KEY not set — see eval/LIVE_EXTRACTION.md")

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "eval/corpus/sample"
    cases = load_corpus(corpus_dir)

    sys.path.insert(0, str(loader.EXTRACTION_ROOT))
    from extractors.pdf import PdfExtractor   # heavy deps — imported lazily
    pdf = PdfExtractor()

    def live_extractor(ext, case):
        case_dir = Path(corpus_dir)
        docs_dir = case_dir / case["case_id"] / "docs"
        out = []
        for label in case["documents"]:
            p = docs_dir / label["source_file"]
            if not p.exists():
                raise FileNotFoundError(f"{p} — run: python eval/generate_corpus.py --pdf")
            out.append(pdf.extract(p))
        return out

    result = metrics.run_extractor(cases, live_extractor)
    print(f"\nLive extraction ({os.getenv('VISION_MODEL', 'Qwen/Qwen2.5-VL-72B-Instruct')}) "
          f"on {corpus_dir} ({len(cases)} cases)")
    for key in ("classification", "field", "fusion", "validation"):
        print(f"  {key:<16}{result[key]['accuracy'] * 100:.2f}%")


if __name__ == "__main__":
    main()
