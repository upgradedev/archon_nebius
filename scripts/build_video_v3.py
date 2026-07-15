#!/usr/bin/env python3
"""Build the fact-correct Archon/Nebius presentation as a narrated MP4.

The video is intentionally generated from reviewed slide copy instead of the
older dashboard tour, whose seeded collection/payment examples exceeded the
implemented production scope. Requires: Pillow, edge-tts, ffmpeg, ffprobe.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import subprocess
from pathlib import Path
from textwrap import wrap

import edge_tts
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "demo" / "video-v3-work"
OUT = ROOT / "demo" / "archon-nebius-presentation-v3.mp4"
W, H = 1920, 1080

BG = "#0d2b22"
PANEL = "#123a2f"
PANEL_2 = "#0f3528"
EMERALD = "#34d399"
WHITE = "#ffffff"
GRAY = "#b7c0c8"
LINE = "#2a5e4d"
AMBER = "#fbbf24"
PURPLE = "#c4b5fd"
RED = "#fca5a5"


SLIDES = [
    {
        "title": "Archon",
        "subtitle": "From financial documents to controlled records",
        "kind": "questions",
        "items": [
            ("What is this?", "Automatic extraction and document classification"),
            ("Where does it belong?", "Company ownership and human review"),
            ("What belongs together?", "Documents linked into financial events"),
            ("What is missing?", "Named controls with source-file evidence"),
        ],
        "narration": "Small-business finance begins with documents, not dashboards. Someone must decide what each file is, where it belongs, whether it belongs to the company, and whether the evidence is complete. Is this a supplier invoice or a sales invoice? Which records describe the same event? Does every payroll document agree? Archon turns those questions into a controlled workflow.",
    },
    {
        "title": "Extraction first; review before analysis",
        "subtitle": "The implemented order and the current failed-file UI gap",
        "kind": "flow",
        "items": [
            ("1. Extract", "PDF · DOCX · scan · image"),
            ("2. Classify", "type · entity · category"),
            ("3. Link + validate", "payroll event · R1–R4"),
            ("4. Review", "successful docs · correct · exclude"),
            ("5. Analyze", "approved period set"),
        ],
        "footer": "Failed-file metadata is recorded in artifacts and logs, but is not shown in the current review UI.",
        "narration": "Archon accepts mixed PDFs, DOCX files, scans, and images. Before review, extraction creates structured fields, refines document types, links the payroll event, and applies R one through R four. The review UI then lets the user correct or exclude successfully extracted records before analysis. Failed-file metadata is recorded in Object Storage and logs, but the current review interface does not display or preserve that list.",
    },
    {
        "title": "Payroll is one linking example",
        "subtitle": "Complementary records linked as one controlled event",
        "kind": "payroll",
        "items": [
            ("Bank confirmation", "Net transfer and payment date"),
            ("Payroll register", "Gross pay · employer cost · headcount"),
            ("Payslips", "Employee-level net amounts"),
            ("One PayrollEvent", "R1 amount · R2 ratio · R3 date · R4 headcount"),
        ],
        "narration": "Payroll is one proof of the financial-document control pattern. A bank confirmation, payroll register, and payslips describe different parts of the same payroll event. Archon groups them by company and period. Four deterministic rules compare net totals, the expected cost ratio, the payment date, and headcount. Every result names the rule and source files.",
    },
    {
        "title": "Supplier completeness — precise boundary",
        "subtitle": "A unit-tested analysis component that is not wired end to end",
        "kind": "boundary",
        "items": [
            ("IMPLEMENTED", "Pre-structured statement entries\nvs recorded invoice numbers and totals"),
            ("FLAGS", "Missing invoice records\nUnmatched uploads\nBalance discrepancy"),
            ("NOT WIRED", "Current extractors do not produce\nstatement entries or balances"),
        ],
        "narration": "The unit-tested supplier Reconciliation Agent compares pre-structured statement entries with invoice numbers and totals already present in the system. It can surface missing or unmatched invoice records and a balance discrepancy. The current extractors and review UI do not populate those statement fields, so this is not an end-to-end user flow and is not a bank-payment matcher. Settlement, collection, duplicate-payment, and remittance matching remain future work.",
    },
    {
        "title": "Deployed path and designed AI Jobs path",
        "subtitle": "Live inline Endpoint execution is separate from the unexecuted Jobs design",
        "kind": "architecture",
        "items": [
            ("CPU AI Endpoint", "FastAPI · live inline subprocess runner"),
            ("Extraction package", "AI Job design · inline in live Endpoint"),
            ("Analysis package", "AI Job design · inline in live Endpoint"),
            ("Inference API", "Qwen2.5-VL vision · Llama 3.3 narrative"),
            ("State & images", "Object Storage · PostgreSQL\nNebius Registry: Job images · GHCR: Endpoint"),
        ],
        "narration": "A Nebius CPU AI Endpoint hosts the FastAPI backend and currently runs extraction and analysis as isolated subprocesses because this tenant has zero CPU Jobs quota. The same packages are implemented as separate AI Job entry points, but no successful Job run is claimed. Qwen two-point-five Vision and Llama three-point-three use the Nebius Inference API. Object Storage is authoritative, PostgreSQL is a best-effort mirror, Nebius Container Registry hosts the two Job images, and G H C R hosts the Endpoint image. Firebase is the browser edge.",
    },
    {
        "title": "Small agents; deterministic finance",
        "subtitle": "The model reads and narrates — Python computes and controls",
        "kind": "pipelines",
        "items": [
            ("Extraction · 4 agents", "Extract → Classify → Link → Validate"),
            ("Analysis · 7 agents", "Classify → P&L → Cash flow → Validate → Employees → Reconcile → Narrate"),
            ("Failure boundary", "If narration fails, the records and report still exist"),
        ],
        "narration": "The extraction pipeline separates extraction, classification, event linking, and validation. The analysis pipeline separates classification, financial aggregation, cash flow, validation, employee analytics, structured supplier reconciliation, and narration. The language model handles unstructured input and readable output. Python performs the sums and named controls. If narration fails, the financial record and report still exist.",
    },
    {
        "title": "What the evaluation proves",
        "subtitle": "A downstream ceiling and a sensitivity test — not a live-vision accuracy claim",
        "kind": "evaluation",
        "items": [
            ("Classification", "100.00%", "74.29%"),
            ("Selected fields", "100.00%", "77.62%"),
            ("Payroll fusion", "100.00%", "54.05%"),
            ("Rules repaired", "0 / 37", "37 / 37"),
        ],
        "narration": "An offline harness imports the real pipeline agents and scores them on forty labelled synthetic payroll cases. With deterministic perfect input, selected-field, classification, and payroll-fusion accuracy reach one hundred percent. That is a downstream ceiling, not a claim of perfect live vision extraction. A degraded extractor makes the scores fall. The harness also exposed dormant rules at zero of thirty-seven; after the missing fields were mapped, the same rules measured thirty-seven of thirty-seven.",
    },
    {
        "title": "The Serverless operations lesson",
        "subtitle": "A submitted Job ID is not proof that compute was provisioned",
        "kind": "operations",
        "items": [
            ("1", "Submit rejected", "Capacity failure → next preset"),
            ("2", "Terminal or vanished, zero instances", "Clean up and try the next preset"),
            ("3", "Still pending when probe ends", "Keep and poll the same Job; no timeout failover"),
            ("4", "Application reached compute", "Surface the bug; do not retry elsewhere"),
        ],
        "narration": "Archon probes for actual provisioning. A creation rejection, or a terminal or vanished Job with zero instances, can advance to another configured preset. If the bounded probe ends while the Job is still pending, Archon keeps and polls that same Job; elapsed time alone does not trigger failover or a duplicate. An application failure after compute starts is surfaced without retrying elsewhere. The live Endpoint uses the inline subprocess path because tenant CPU Jobs quota is zero.",
    },
    {
        "title": "Current proof → explicit next work",
        "subtitle": "A bounded document-control prototype",
        "kind": "close",
        "items": [
            ("TODAY", "Extraction · classification · review\npayroll linking · R1–R4\nvalidation source-file references"),
            ("NEXT", "Invoice ↔ payment · invoice ↔ collection\ntax/contribution remittances\njournal export and accounting integrations"),
        ],
        "narration": "Today, Archon proves automated extraction, deterministic type refinement, human review of successfully extracted documents, payroll-event linking, and four validations with source-file references. Failed-file display, raw supplier-statement ingestion, general invoice-to-payment and collection matching, remittance verification, and journal export are explicit next work. The product is a financial-document control workflow with bounded evidence, with broader matching planned as a future extension.",
    },
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


F_TITLE = font(66, True)
F_SUB = font(30)
F_CARD_H = font(29, True)
F_CARD = font(23)
F_SMALL = font(19)
F_BIG = font(50, True)
F_FOOT = font(20)


def rounded(draw: ImageDraw.ImageDraw, box, fill=PANEL, outline=LINE, width=2, radius=22):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_lines(draw, xy, text, fnt, fill, max_chars=38, spacing=10, anchor=None):
    lines = []
    for para in text.split("\n"):
        lines.extend(wrap(para, max_chars) or [""])
    draw.multiline_text(xy, "\n".join(lines), font=fnt, fill=fill, spacing=spacing, anchor=anchor)


def header(draw, slide, index):
    draw.text((90, 62), slide["title"], font=F_TITLE, fill=WHITE)
    draw.text((92, 145), slide["subtitle"], font=F_SUB, fill=GRAY)
    draw.line((90, 195, 1830, 195), fill=LINE, width=2)
    draw.text((90, 1030), "#NebiusServerlessChallenge", font=F_FOOT, fill=EMERALD)
    draw.text((1830, 1030), f"{index:02d} / {len(SLIDES):02d}", font=F_FOOT, fill=GRAY, anchor="ra")


def render_slide(slide, index, path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    header(d, slide, index)
    kind = slide["kind"]

    if kind == "questions":
        coords = [(100, 250, 930, 540), (990, 250, 1820, 540), (100, 600, 930, 890), (990, 600, 1820, 890)]
        for (h, body), box in zip(slide["items"], coords):
            rounded(d, box)
            d.text((box[0]+36, box[1]+38), h, font=F_CARD_H, fill=EMERALD)
            draw_lines(d, (box[0]+36, box[1]+105), body, F_CARD, WHITE, 45, 11)

    elif kind == "flow":
        x, y, bw, bh, gap = 70, 350, 310, 300, 55
        colors = [PANEL, PANEL, "#2a2210", PANEL, PANEL_2]
        outlines = [LINE, LINE, AMBER, LINE, EMERALD]
        for i, ((h, body), color, out) in enumerate(zip(slide["items"], colors, outlines)):
            box = (x+i*(bw+gap), y, x+i*(bw+gap)+bw, y+bh)
            rounded(d, box, color, out)
            d.text((box[0]+26, box[1]+42), h, font=F_CARD_H, fill=EMERALD if i != 2 else AMBER)
            draw_lines(d, (box[0]+26, box[1]+115), body, F_CARD, WHITE, 24, 10)
            if i < 4:
                d.text((box[2]+14, y+118), "→", font=F_BIG, fill=EMERALD)
        draw_lines(
            d,
            (W//2, 760),
            slide.get("footer", "The reviewer decides which successfully extracted records proceed."),
            F_CARD_H,
            WHITE,
            82,
            anchor="ma",
        )

    elif kind == "payroll":
        cards = slide["items"][:3]
        for i, (h, body) in enumerate(cards):
            x = 90 + i*600
            rounded(d, (x, 260, x+530, 500))
            d.text((x+30, 302), h, font=F_CARD_H, fill=PURPLE)
            draw_lines(d, (x+30, 375), body, F_CARD, WHITE, 35)
            d.line((x+265, 500, 960, 620), fill=EMERALD, width=5)
        rounded(d, (430, 620, 1490, 890), PANEL_2, EMERALD, 3)
        h, body = slide["items"][3]
        d.text((960, 670), h, font=F_BIG, fill=EMERALD, anchor="ma")
        draw_lines(d, (960, 755), body, F_CARD_H, WHITE, 64, anchor="ma")

    elif kind == "boundary":
        colors = [PANEL_2, PANEL, "#2a2210"]
        outs = [EMERALD, PURPLE, AMBER]
        for i, ((h, body), color, out) in enumerate(zip(slide["items"], colors, outs)):
            x = 90 + i*600
            rounded(d, (x, 260, x+540, 820), color, out, 3)
            d.text((x+35, 310), h, font=F_CARD_H, fill=out)
            draw_lines(d, (x+35, 395), body, F_CARD_H, WHITE, 32, 20)
        d.text((960, 910), "Current build ≠ general bank-payment matching", font=F_CARD_H, fill=RED, anchor="ma")

    elif kind == "architecture":
        # The compact architecture is redrawn so the slide remains legible on video.
        ex = [(90, 260, 570, 500), (720, 260, 1200, 500), (1350, 260, 1830, 500)]
        labels = slide["items"][:3]
        for i, ((h, body), box) in enumerate(zip(labels, ex)):
            rounded(d, box, PANEL_2 if i else PANEL, EMERALD)
            d.text((box[0]+32, box[1]+42), h, font=F_CARD_H, fill=EMERALD)
            draw_lines(d, (box[0]+32, box[1]+112), body, F_CARD, WHITE, 30)
            if i < 2:
                d.text((box[2]+50, 345), "→", font=F_BIG, fill=EMERALD)
        for i, (h, body) in enumerate(slide["items"][3:]):
            box = (230+i*850, 620, 840+i*850, 860)
            rounded(d, box, PANEL, PURPLE if i == 0 else LINE)
            d.text((box[0]+32, box[1]+35), h, font=F_CARD_H, fill=PURPLE if i == 0 else EMERALD)
            draw_lines(d, (box[0]+32, box[1]+105), body, F_CARD, WHITE, 42)

    elif kind == "pipelines":
        boxes = [(100, 260, 1820, 475), (100, 535, 1820, 750), (290, 815, 1630, 930)]
        for i, ((h, body), box) in enumerate(zip(slide["items"], boxes)):
            rounded(d, box, PANEL_2 if i < 2 else "#2a2210", EMERALD if i < 2 else AMBER)
            d.text((box[0]+35, box[1]+36), h, font=F_CARD_H, fill=EMERALD if i < 2 else AMBER)
            draw_lines(d, (box[0]+35, box[1]+105), body, F_CARD_H, WHITE, 85)

    elif kind == "evaluation":
        d.text((805, 255), "Perfect-input ceiling", font=F_CARD_H, fill=EMERALD, anchor="ma")
        d.text((1195, 255), "Degraded sensitivity", font=F_CARD_H, fill=GRAY, anchor="ma")
        y = 320
        for metric, ceiling, degraded in slide["items"]:
            rounded(d, (180, y, 1740, y+125), PANEL if metric != "Rules repaired" else "#2a2210", LINE if metric != "Rules repaired" else AMBER)
            d.text((225, y+40), metric, font=F_CARD_H, fill=WHITE)
            d.text((805, y+38), ceiling, font=F_CARD_H, fill=EMERALD if metric != "Rules repaired" else RED, anchor="ma")
            d.text((1195, y+38), degraded, font=F_CARD_H, fill=GRAY if metric != "Rules repaired" else EMERALD, anchor="ma")
            y += 145
        d.text((960, 930), "40 labelled synthetic payroll cases · real downstream agents · offline", font=F_CARD, fill=GRAY, anchor="ma")

    elif kind == "operations":
        y = 260
        for ident, h, body in slide["items"]:
            rounded(d, (160, y, 1760, y+145), PANEL_2 if ident != "Fallback" else "#2a2210", EMERALD if ident != "Fallback" else AMBER)
            d.text((210, y+42), ident, font=F_CARD_H, fill=EMERALD if ident != "Fallback" else AMBER)
            d.text((450, y+42), h, font=F_CARD_H, fill=WHITE)
            draw_lines(d, (1050, y+42), body, F_CARD, GRAY, 48)
            y += 165

    elif kind == "proof":
        boxes = [(120, 255, 1800, 440), (120, 485, 1800, 670), (120, 715, 1800, 900)]
        outlines = [EMERALD, PURPLE, AMBER]
        for (h, body), box, out in zip(slide["items"], boxes, outlines):
            rounded(d, box, PANEL_2 if out != AMBER else "#2a2210", out, 3)
            d.text((box[0]+38, box[1]+32), h, font=F_CARD_H, fill=out)
            draw_lines(d, (box[0]+38, box[1]+92), body, F_CARD, WHITE, 105, 8)
        if slide.get("footer"):
            d.text((960, 955), slide["footer"], font=F_SMALL, fill=GRAY, anchor="ma")

    elif kind == "close":
        for i, (h, body) in enumerate(slide["items"]):
            x = 120 + i*880
            rounded(d, (x, 280, x+800, 830), PANEL_2 if i == 0 else "#2a2210", EMERALD if i == 0 else AMBER, 3)
            d.text((x+45, 335), h, font=F_BIG, fill=EMERALD if i == 0 else AMBER)
            draw_lines(d, (x+45, 460), body, F_CARD_H, WHITE, 42, 22)
        d.text((960, 920), "github.com/upgradedev/archon_nebius", font=F_CARD_H, fill=EMERALD, anchor="ma")

    im.save(path, quality=95)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


async def synthesize(text: str, path: Path):
    communicate = edge_tts.Communicate(text, "en-US-GuyNeural", rate="-4%", pitch="-2Hz")
    await communicate.save(str(path))


def run(cmd):
    print(" ".join(map(str, cmd)))
    subprocess.run(list(map(str, cmd)), check=True)


async def main():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise SystemExit(f"{exe} not found")
    WORK.mkdir(parents=True, exist_ok=True)

    manifest = []
    for idx, slide in enumerate(SLIDES, 1):
        png = WORK / f"slide-{idx:02d}.png"
        mp3 = WORK / f"slide-{idx:02d}.mp3"
        mp4 = WORK / f"segment-{idx:02d}.mp4"
        render_slide(slide, idx, png)
        await synthesize(slide["narration"], mp3)
        audio_len = duration(mp3)
        seg_len = math.ceil((audio_len + 1.1) * 10) / 10
        fade_out = max(seg_len - 0.45, 0.1)
        vf = f"scale={W}:{H},fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.2f}:d=0.35,format=yuv420p"
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", png, "-i", mp3,
            "-vf", vf, "-filter_complex", "[1:a]apad=pad_dur=1.1[a]",
            "-map", "0:v", "-map", "[a]", "-t", f"{seg_len:.2f}",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", mp4,
        ])
        manifest.append({"slide": idx, "title": slide["title"], "audio_seconds": audio_len, "segment_seconds": seg_len})

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{(WORK / f'segment-{i:02d}.mp4').as_posix()}'\n" for i in range(1, len(SLIDES)+1)), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", "-movflags", "+faststart", OUT])
    (WORK / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"WROTE {OUT} ({duration(OUT):.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())
