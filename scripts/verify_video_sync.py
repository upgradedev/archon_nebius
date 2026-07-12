#!/usr/bin/env python3
"""Audio/video/caption sync gate for the Archon demo video.

The demo video is assembled by .github/workflows/demo-video.yml as:

    [ title card (3s) ] + [ captioned tour (TOUR_LEN) ] + [ outro card (3s) ]

with the ElevenLabs voiceover muxed on top, delayed by the 3s title. The tour's
fixed beats (scripts/demo-tour.mjs BEATS) and burned captions (scripts/captions.txt)
share one timeline that ends at REPRO_END=300, then a call-to-action slide is held
until TARGET. For the video to stay in sync the *voiceover* must land close to the
beat/caption timeline — if the narration is much longer than the timeline the
call-to-action slide is held for a long, static tail while the voice keeps talking
(the exact drift this gate exists to catch).

Checks (all must pass):
  1. voiceover ends before the tour does (VO never clipped)                — if a voiceover file is given
  2. voiceover is close to the tour length (audio ~= video beats)          — if a voiceover file is given
  3. captions never bleed past the tour into the outro                     — always
  4. the call-to-action tail (tour_len - REPRO_END) is short (a real beat, — always
     not minutes of dead air)
  5. the final mp4 length is a sane ~5-6 min analytical cut                 — always

Usage:
  python scripts/verify_video_sync.py --mp4 demo/archon-nebius-demo.mp4 \
      [--voiceover archon-voiceover.mp3] [--captions scripts/captions.txt]

Exit code 0 = PASS, 1 = FAIL. Requires ffprobe on PATH.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TITLE = 3.0          # title card seconds (demo-video.yml)
OUTRO = 3.0          # outro card seconds (demo-video.yml)
REPRO_END = 300.0    # last content beat; CTA is held from here to TARGET (demo-tour.mjs)
CTA_TAIL_MAX = 25.0  # the CTA is a real ~14s beat; anything much longer is drift/dead air
VO_GAP_MAX = 25.0    # how far the voiceover may fall short of the tour length
MP4_MIN, MP4_MAX = 280.0, 400.0  # a ~5-6 min cut (Nebius target is 3-10 min)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def caption_max_end(path: Path) -> float:
    end = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            try:
                end = max(end, float(parts[1]))
            except ValueError:
                pass
    return end


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp4", default="demo/archon-nebius-demo.mp4")
    ap.add_argument("--voiceover", default=None)
    ap.add_argument("--captions", default="scripts/captions.txt")
    args = ap.parse_args()

    if not shutil.which("ffprobe"):
        print("FAIL: ffprobe not found on PATH", file=sys.stderr)
        return 1

    mp4 = Path(args.mp4)
    caps = Path(args.captions)
    if not mp4.exists():
        print(f"FAIL: mp4 not found: {mp4}", file=sys.stderr)
        return 1

    mp4_dur = duration(mp4)
    tour_len = mp4_dur - TITLE - OUTRO
    cap_end = caption_max_end(caps)
    cta_tail = tour_len - REPRO_END

    checks: list[tuple[bool, str]] = []
    checks.append((MP4_MIN <= mp4_dur <= MP4_MAX,
                   f"mp4 length {mp4_dur:.1f}s in [{MP4_MIN:.0f},{MP4_MAX:.0f}]"))
    checks.append((cap_end <= tour_len + 0.5,
                   f"captions end {cap_end:.1f}s <= tour {tour_len:.1f}s (no bleed into outro)"))
    checks.append((cta_tail <= CTA_TAIL_MAX,
                   f"CTA tail {cta_tail:.1f}s <= {CTA_TAIL_MAX:.0f}s (no static dead-air tail)"))

    if args.voiceover:
        vo = Path(args.voiceover)
        if not vo.exists():
            print(f"FAIL: voiceover not found: {vo}", file=sys.stderr)
            return 1
        vo_dur = duration(vo)
        checks.append((vo_dur <= tour_len + 0.5,
                       f"voiceover {vo_dur:.1f}s <= tour {tour_len:.1f}s (VO not clipped)"))
        checks.append((tour_len - vo_dur <= VO_GAP_MAX,
                       f"tour - voiceover = {tour_len - vo_dur:.1f}s <= {VO_GAP_MAX:.0f}s (audio ~= video beats)"))

    ok = True
    for passed, msg in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {msg}")
        ok = ok and passed

    print("SYNC GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
