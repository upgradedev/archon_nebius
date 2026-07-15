#!/usr/bin/env python3
"""Build the Archon blog PDF from blog-post.md + article-figures.

  python demo/build_blog_pdf.py     # writes demo/archon-nebius-blog.pdf

Markdown -> HTML (python-markdown) with the four PNG figures embedded as base64,
then Playwright/Chromium renders the HTML to A4 PDF. Run from repos/nebius.
Requires: pip install markdown ; node playwright (in ./frontend).
"""
import base64, pathlib, subprocess
import markdown

DEMO = pathlib.Path(__file__).resolve().parent           # repos/nebius/demo
REPO = DEMO.parent                                       # repos/nebius
BLOG = DEMO / "blog-post.md"
PNG = DEMO / "article-figures" / "png"
OUT_HTML = DEMO / "archon-nebius-blog.html"              # generated (gitignored)
OUT_PDF = DEMO / "archon-nebius-blog.pdf"


def b64(name: str) -> str:
    return "data:image/png;base64," + base64.b64encode((PNG / name).read_bytes()).decode()


def fig(name: str, cap: str) -> str:
    return f'<figure><img src="{b64(name)}"/><figcaption>{cap}</figcaption></figure>'


CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  font-size: 11pt; line-height: 1.55; color: #1a1a1a; }
h1 { font-size: 22pt; line-height: 1.2; margin: 0 0 4pt; }
h2 { font-size: 15pt; margin: 24pt 0 8pt; padding-top: 8pt; border-top: 1px solid #e5e7eb; }
p { margin: 0 0 9pt; }
code { font-family: 'Cascadia Code','Consolas',monospace; font-size: 9.5pt;
  background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }
pre { background: #0d1117; color: #e6edf3; padding: 12px 14px; border-radius: 8px;
  font-size: 8.5pt; line-height: 1.5; page-break-inside: avoid;
  white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }
pre code { background: none; color: inherit; padding: 0; font-size: inherit; white-space: inherit; }
table { border-collapse: collapse; width: 100%; margin: 10pt 0; font-size: 10pt; }
th, td { border: 1px solid #d1d5db; padding: 6px 10px; text-align: left; }
th { background: #f3f4f6; }
blockquote { margin: 10pt 0; padding: 8pt 12pt; background: #eef2ff;
  border-left: 3px solid #6366f1; border-radius: 4px; font-size: 10pt; }
figure { margin: 20pt 0 24pt; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; }
figcaption { font-size: 9pt; color: #6b7280; margin-top: 10pt; line-height: 1.45;
  padding: 0 8pt; max-width: 92%; margin-left: auto; margin-right: auto; }
a { color: #4f46e5; text-decoration: none; }
hr { border: none; border-top: 1px solid #e5e7eb; margin: 16pt 0; }
"""


def main() -> None:
    html = markdown.markdown(BLOG.read_text(encoding="utf-8"), extensions=["fenced_code", "tables"])
    html = html.replace("</blockquote>", "</blockquote>\n" + fig(
        "fig-1-architecture.png",
        "Figure 1. Archon spans a Firebase public edge and Nebius backend services."), 1)
    html = html.replace("<h2>The insight", fig(
        "fig-2-payroll-gap.png",
        "Figure 2. Three payroll documents fused into one event, reconciling the full "
        "employer cost (about 72% above the bank transfer).") + "\n<h2>The insight", 1)
    html = html.replace("<h2>Two agent pipelines", fig(
        "fig-3-pipeline.png",
        "Figure 3. Upload, extraction, analysis, dashboard: the on-demand job pipeline.")
        + "\n<h2>Two agent pipelines", 1)
    html = html.replace("<h2>Why Nebius Serverless AI", fig(
        "fig-4-cost-model.png",
        "Figure 4. CPU endpoint and CPU jobs call the Nebius Inference API instead of an "
        "always-on GPU.") + "\n<h2>Why Nebius Serverless AI", 1)
    OUT_HTML.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
        f"<body>{html}</body></html>", encoding="utf-8")

    render = (
        "import { chromium } from 'playwright';\n"
        "const b = await chromium.launch();\n"
        "const p = await b.newPage();\n"
        f"await p.goto('file://{OUT_HTML.as_posix()}', {{ waitUntil: 'networkidle' }});\n"
        f"await p.pdf({{ path: '{OUT_PDF.as_posix()}', format: 'A4', printBackground: true,\n"
        "  margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' } });\n"
        "await b.close(); console.log('PDF written');\n"
    )
    front = REPO / "frontend"
    script = front / "_build_pdf.mjs"
    script.write_text(render, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(script)], cwd=str(front), capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip()[-300:])
    finally:
        script.unlink(missing_ok=True)
    print("PDF written:", OUT_PDF, OUT_PDF.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
