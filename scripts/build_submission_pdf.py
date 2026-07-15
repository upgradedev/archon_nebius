#!/usr/bin/env python3
"""Build the final Challenge blog PDF from ``demo/blog-post.md``.

The Challenge form requires a PDF export of the public article.  This builder
uses ReportLab so the artifact is deterministic and does not depend on a local
browser.  By default it writes:

    output/pdf/archon-nebius-devto-article.pdf

Pass ``--sync-demo`` to also replace the repository copy at
``demo/archon-nebius-blog.pdf`` after the final article has been approved.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.utils import ImageReader


REPO = Path(__file__).resolve().parents[1]
BLOG = REPO / "demo" / "blog-post.md"
FIGURES = REPO / "demo" / "article-figures" / "png"
DEFAULT_OUT = REPO / "output" / "pdf" / "archon-nebius-devto-article.pdf"
DEMO_OUT = REPO / "demo" / "archon-nebius-blog.pdf"


def register_fonts() -> dict[str, str]:
    """Register Windows fonts when available, with safe built-in fallbacks."""
    candidates = {
        "body": (Path(r"C:\Windows\Fonts\arial.ttf"), "ArchonArial", "Helvetica"),
        "bold": (Path(r"C:\Windows\Fonts\arialbd.ttf"), "ArchonArialBold", "Helvetica-Bold"),
        "italic": (Path(r"C:\Windows\Fonts\ariali.ttf"), "ArchonArialItalic", "Helvetica-Oblique"),
        "mono": (Path(r"C:\Windows\Fonts\consola.ttf"), "ArchonConsolas", "Courier"),
    }
    result: dict[str, str] = {}
    for role, (path, name, fallback) in candidates.items():
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            result[role] = name
        else:
            result[role] = fallback
    return result


def normalize(text: str) -> str:
    """Keep PDF typography portable and follow the ASCII-hyphen requirement."""
    return (
        text.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u00b7", " | ")
    )


def inline_markup(text: str, fonts: dict[str, str]) -> str:
    text = html.escape(normalize(text.strip()))
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" color="#3657c8">\1</a>',
        text,
    )
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f'<font name="{fonts["mono"]}" color="#243047">{m.group(1)}</font>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


def make_styles(fonts: dict[str, str]):
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName=fonts["body"],
        fontSize=9.6,
        leading=14.2,
        textColor=colors.HexColor("#172033"),
        spaceAfter=6.5,
        alignment=TA_LEFT,
    )
    return {
        "title": ParagraphStyle(
            "Title",
            parent=body,
            fontName=fonts["bold"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#111827"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=body,
            fontName=fonts["italic"],
            fontSize=11.2,
            leading=15,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=body,
            fontName=fonts["bold"],
            fontSize=15.5,
            leading=19,
            textColor=colors.HexColor("#18234a"),
            spaceBefore=13,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "body": body,
        "quote": ParagraphStyle(
            "Quote",
            parent=body,
            fontSize=9.2,
            leading=13.5,
            leftIndent=10,
            rightIndent=8,
            borderColor=colors.HexColor("#6475d9"),
            borderWidth=0.8,
            borderPadding=7,
            backColor=colors.HexColor("#f0f2ff"),
            spaceBefore=4,
            spaceAfter=9,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=body,
            fontName=fonts["mono"],
            fontSize=7.4,
            leading=10.2,
            textColor=colors.HexColor("#172033"),
            backColor=colors.HexColor("#eef2f7"),
            borderPadding=8,
            leftIndent=6,
            rightIndent=6,
            spaceBefore=4,
            spaceAfter=9,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=body,
            fontSize=8.2,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#667085"),
            spaceBefore=4,
            spaceAfter=10,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=body,
            fontSize=7.8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#7b8495"),
        ),
    }


def figure(name: str, caption: str, styles, max_width: float) -> KeepTogether:
    path = FIGURES / name
    if not path.exists():
        raise FileNotFoundError(f"Missing article figure: {path}")
    width, height = ImageReader(str(path)).getSize()
    scale = min(max_width / width, 88 * mm / height, 1.0)
    img = Image(str(path), width=width * scale, height=height * scale)
    img.hAlign = "CENTER"
    return KeepTogether(
        [Spacer(1, 4), img, Paragraph(inline_markup(caption, FONTS), styles["caption"])]
    )


def parse_table(lines: list[str], start: int, styles) -> tuple[Table, int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
            rows.append([Paragraph(inline_markup(c, FONTS), styles["body"]) for c in cells])
        i += 1
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#18234a")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8cfdd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table, i


def parse_markdown(text: str, styles, content_width: float):
    lines = normalize(text).splitlines()
    story = []
    i = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        joined = " ".join(part.strip() for part in paragraph).strip()
        if joined:
            story.append(Paragraph(inline_markup(joined, FONTS), styles["body"]))
            if joined.startswith("That review gate is deliberate"):
                story.append(
                    figure(
                        "fig-2-control-loop.png",
                        "Figure 2. Archon keeps a human review gate between extraction and financial analysis.",
                        styles,
                        content_width,
                    )
                )
        paragraph.clear()

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line:
            flush_paragraph()
            i += 1
            continue

        if line.startswith("```"):
            flush_paragraph()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            story.append(Preformatted("\n".join(code), styles["code"], maxLineLength=110))
            i += 1
            continue

        # DEV renders these external PNG references directly. The PDF inserts the
        # same local figures at deliberate section boundaries below, so skip the
        # Markdown image line here to avoid duplicate figures or raw alt text.
        if re.fullmatch(r"!\[[^\]]*\]\([^)]+\)", line):
            flush_paragraph()
            i += 1
            continue

        if line.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:], FONTS), styles["title"]))
            i += 1
            continue

        if line.startswith("## "):
            flush_paragraph()
            heading = line[3:].strip()
            story.append(Paragraph(inline_markup(heading, FONTS), styles["h2"]))
            if heading.startswith("Why Nebius Serverless AI"):
                story.append(
                    figure(
                        "fig-4-cost-model.png",
                        "Figure 4. The live build uses a CPU Endpoint and managed inference; extraction and analysis are dispatched as on-demand AI Jobs with bounded cross-region provisioning.",
                        styles,
                        content_width,
                    )
                )
            if heading.startswith("Two single-responsibility pipelines"):
                story.append(
                    figure(
                        "fig-3-pipeline.png",
                        "Figure 3. Both pipelines run as AI Jobs and share artifact and status contracts; inline execution is an emergency fallback only.",
                        styles,
                        content_width,
                    )
                )
            i += 1
            continue

        if line.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            story.append(Paragraph(inline_markup(" ".join(quote_lines), FONTS), styles["quote"]))
            if "Architecture diagram" in " ".join(quote_lines):
                story.append(
                    figure(
                        "fig-1-architecture.png",
                        "Figure 1. Archon spans a Firebase browser edge and Nebius backend services, with AI Job dispatch routed through explicit project-region-subnet placements.",
                        styles,
                        content_width,
                    )
                )
            continue

        if line == "---":
            flush_paragraph()
            story.append(Spacer(1, 7))
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            flush_paragraph()
            table, i = parse_table(lines, i, styles)
            story.extend([table, Spacer(1, 8)])
            continue

        if re.match(r"^[-*] ", line):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i].strip()):
                content = re.sub(r"^[-*] ", "", lines[i].strip())
                items.append(ListItem(Paragraph(inline_markup(content, FONTS), styles["body"])))
                i += 1
            story.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    start="circle",
                    leftIndent=17,
                    bulletFontName=FONTS["body"],
                    bulletFontSize=6,
                    spaceAfter=6,
                )
            )
            continue

        if re.match(r"^\d+\. ", line):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i].strip()):
                content = re.sub(r"^\d+\. ", "", lines[i].strip())
                items.append(ListItem(Paragraph(inline_markup(content, FONTS), styles["body"])))
                i += 1
            story.append(ListFlowable(items, bulletType="1", leftIndent=19, spaceAfter=6))
            continue

        if line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line, FONTS), styles["subtitle"]))
            i += 1
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    return story


def page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d7dce6"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.setFont(FONTS["body"], 7.8)
    canvas.setFillColor(colors.HexColor("#7b8495"))
    canvas.drawString(18 * mm, 8.5 * mm, "Archon | Nebius Serverless AI Builders Challenge 2026")
    canvas.drawRightString(A4[0] - 18 * mm, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    left = right = 18 * mm
    top = 17 * mm
    bottom = 18 * mm
    width = A4[0] - left - right
    height = A4[1] - top - bottom
    doc = BaseDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title="Building Archon: From Financial Documents to Controlled Records on Nebius Serverless AI",
        author="Archon",
        subject="Nebius Serverless AI Builders Challenge 2026",
    )
    frame = Frame(left, bottom, width, height, id="main")
    doc.addPageTemplates([PageTemplate(id="article", frames=[frame], onPage=page_footer)])
    styles = make_styles(FONTS)
    story = parse_markdown(BLOG.read_text(encoding="utf-8"), styles, width)
    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sync-demo", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    build(out)
    if args.sync_demo:
        shutil.copy2(out, DEMO_OUT)
    print(f"PDF written: {out} ({out.stat().st_size} bytes)")
    if args.sync_demo:
        print(f"Repository copy updated: {DEMO_OUT}")


FONTS = register_fonts()


if __name__ == "__main__":
    main()
