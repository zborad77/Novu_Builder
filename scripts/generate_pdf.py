"""
Generate a print-ready PDF from a markdown source using headless Chrome.

This script is intentionally lightweight and dependency-free. It renders a
subset of markdown used by project documents:

- # / ## / ### headings
- paragraphs
- unordered lists
- ordered lists
- horizontal rules
- inline **bold**

Usage:
  python scripts/generate_pdf.py
  python scripts/generate_pdf.py --input docs/file.md --output docs/file.pdf
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
from pathlib import Path


DEFAULT_INPUT = Path("docs") / "NOVU_Builder_Brozura_2026-04-10.md"
DEFAULT_OUTPUT = Path("docs") / "NOVU_Builder_Brozura_2026-04-10.pdf"


def find_chrome() -> str:
    candidates = [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Chrome/Edge executable not found for PDF export.")


def inline_markup(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def markdown_to_html(markdown_text: str, title: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph_buffer: list[str] = []
    list_items: list[str] = []
    list_type: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        text = " ".join(part.strip() for part in paragraph_buffer if part.strip())
        blocks.append(f"<p>{inline_markup(text)}</p>")
        paragraph_buffer = []

    def flush_list() -> None:
        nonlocal list_items, list_type
        if not list_items or not list_type:
            return
        items_html = "".join(f"<li>{item}</li>" for item in list_items)
        blocks.append(f"<{list_type}>{items_html}</{list_type}>")
        list_items = []
        list_type = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if re.fullmatch(r"-{3,}", stripped):
            flush_paragraph()
            flush_list()
            blocks.append("<hr>")
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{inline_markup(stripped[4:])}</h3>")
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{inline_markup(stripped[3:])}</h2>")
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h1>{inline_markup(stripped[2:])}</h1>")
            continue

        unordered_match = re.match(r"^[-*]\s+(.*)$", stripped)
        if unordered_match:
            flush_paragraph()
            if list_type not in (None, "ul"):
                flush_list()
            list_type = "ul"
            list_items.append(inline_markup(unordered_match.group(1)))
            continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            flush_paragraph()
            if list_type not in (None, "ol"):
                flush_list()
            list_type = "ol"
            list_items.append(inline_markup(ordered_match.group(1)))
            continue

        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()

    body = "\n".join(blocks)

    return f"""<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 16mm 18mm 16mm;
    }}

    :root {{
      --ink: #17202a;
      --muted: #4b5563;
      --accent: #0f3f7f;
      --rule: #c8d2de;
      --bg: #ffffff;
      --panel: #f5f8fc;
    }}

    html, body {{
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.45;
      margin: 0;
      padding: 0;
    }}

    body {{
      padding: 0;
    }}

    h1, h2, h3 {{
      break-after: avoid-page;
      page-break-after: avoid;
      margin-top: 0;
      color: var(--ink);
    }}

    h1 {{
      font-size: 24pt;
      line-height: 1.15;
      margin-bottom: 10pt;
      color: var(--accent);
    }}

    h2 {{
      font-size: 16pt;
      margin-top: 22pt;
      margin-bottom: 8pt;
      padding-bottom: 4pt;
      border-bottom: 1px solid var(--rule);
      color: var(--accent);
    }}

    h3 {{
      font-size: 12pt;
      margin-top: 14pt;
      margin-bottom: 6pt;
    }}

    p {{
      margin: 0 0 8pt 0;
      color: var(--muted);
      text-align: left;
    }}

    strong {{
      color: var(--ink);
      font-weight: 700;
    }}

    ul, ol {{
      margin: 0 0 10pt 20pt;
      padding: 0;
      color: var(--muted);
    }}

    li {{
      margin: 0 0 4pt 0;
    }}

    hr {{
      border: 0;
      border-top: 1px solid var(--rule);
      margin: 14pt 0;
    }}

    .doc {{
      width: 100%;
    }}

    .cover {{
      min-height: 240mm;
      display: flex;
      flex-direction: column;
      justify-content: center;
      page-break-after: always;
      border-top: 6px solid var(--accent);
      padding-top: 18mm;
      box-sizing: border-box;
    }}

    .cover-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 9pt;
      color: var(--accent);
      margin-bottom: 10pt;
    }}

    .cover-title {{
      font-size: 30pt;
      line-height: 1.08;
      font-weight: 700;
      color: var(--ink);
      margin: 0 0 8pt 0;
    }}

    .cover-subtitle {{
      font-size: 13pt;
      line-height: 1.35;
      color: var(--muted);
      max-width: 140mm;
      margin-bottom: 22pt;
    }}

    .cover-meta {{
      background: var(--panel);
      border: 1px solid var(--rule);
      padding: 10pt 12pt;
      max-width: 120mm;
      color: var(--muted);
    }}

    .cover-meta div {{
      margin: 0 0 5pt 0;
    }}

    .cover-meta div:last-child {{
      margin-bottom: 0;
    }}

    .content {{
      width: 100%;
    }}
  </style>
</head>
<body>
  <main class="doc">
    <section class="cover">
      <div class="cover-eyebrow">NOVU Builder</div>
      <div class="cover-title">Projektová brožura</div>
      <div class="cover-subtitle">Technicky přesný přehled aktuálního stavu, provozní připravenosti a cílového směru systému pro B2B, investiční a enterprise partnery.</div>
      <div class="cover-meta">
        <div><strong>Dokument:</strong> 10. dubna 2026</div>
        <div><strong>Stav:</strong> controlled pilot / near-production</div>
        <div><strong>Určení:</strong> B2B klienti, investoři, enterprise partneři</div>
      </div>
    </section>
    <section class="content">
      {body}
    </section>
  </main>
</body>
</html>
"""


def run_chrome_print(html_path: Path, pdf_path: Path) -> None:
    chrome_path = find_chrome()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    build_dir = html_path.parent
    profile_dir = build_dir / "chrome-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        chrome_path,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-crash-reporter",
        "--disable-breakpad",
        f"--user-data-dir={str(profile_dir.resolve())}",
        f"--print-to-pdf={str(pdf_path.resolve())}",
        "--print-to-pdf-no-header",
        html_path.resolve().as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "Chrome PDF export failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError("PDF export finished without creating a valid output file.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--title", default="NOVU Builder")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve()
    output_path = args.output.resolve()
    markdown_text = source_path.read_text(encoding="utf-8")
    html_text = markdown_to_html(markdown_text, title=args.title)

    temp_dir = output_path.parent / ".pdf-build"
    temp_dir.mkdir(parents=True, exist_ok=True)
    html_path = temp_dir / f"{output_path.stem}.html"
    html_path.write_text(html_text, encoding="utf-8")
    run_chrome_print(html_path, output_path)

    print(f"Saved PDF: {output_path}")


if __name__ == "__main__":
    main()
