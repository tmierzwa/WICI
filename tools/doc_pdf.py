# SPDX-License-Identifier: MIT
"""Print a repository Markdown document to PDF for people outside the repository.

Usage: python3 tools/doc_pdf.py <document.md> <output.pdf> [--chrome PATH]
Relative links become links to the file on GitHub (main), so the PDF works on its own.
Needs the Python package "markdown" and Chrome or Chromium (--chrome or $CHROME).
A PDF written to output/pdf/ is recorded in output/pdf/zrodla.json with the SHA-256 of its source and of
the PDF itself; tools/verify_repository.py rejects a PDF whose source changed after printing.
"""

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import markdown

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "output/pdf/zrodla.json"
GITHUB = "https://github.com/tmierzwa/WICI/blob/main/"
CHROMES = ["chromium", "chromium-browser", "google-chrome", "chrome",
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
CSS = """
@page { size: A4; margin: 16mm 16mm 14mm; }
body { font: 10pt/1.42 "DejaVu Sans", "Helvetica Neue", Arial, sans-serif; color: #1d1d1b; }
h1 { font-size: 17pt; margin: 0 0 8pt; color: #b5121b; }
h2 { font-size: 12.5pt; margin: 14pt 0 5pt; border-bottom: 1px solid #ccc; padding-bottom: 2pt; }
h2, h3 { break-after: avoid; }
h3 { font-size: 11pt; margin: 10pt 0 4pt; }
p, li { margin: 3pt 0; }
ul, ol { padding-left: 16pt; margin: 3pt 0; }
table { border-collapse: collapse; margin: 5pt 0; font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 2.5pt 6pt; text-align: left; }
th { background: #f0f0ee; }
a { color: #1d1d1b; }
code { font-size: 9pt; }
footer { margin-top: 8pt; font-size: 8pt; color: #666; }
"""


def link(href: str, source: Path) -> str:
    """Relative repository link -> GitHub URL; external links and anchors stay."""
    if re.match(r"^[a-z]+:", href) or href.startswith("#"):
        return href
    path, _, anchor = href.partition("#")
    target = (source.parent / path).resolve().relative_to(ROOT).as_posix()
    return GITHUB + target + (f"#{anchor}" if anchor else "")


def html(source: Path) -> str:
    body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["tables"])
    body = re.sub(r'href="([^"]+)"', lambda m: f'href="{link(m.group(1), source)}"', body)
    url = GITHUB + source.resolve().relative_to(ROOT).as_posix()
    return (f'<!doctype html><html lang="pl"><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f'<body>{body}<footer>Źródło: <a href="{url}">{url}</a></footer></body></html>')


def chrome(explicit: str | None) -> str:
    for name in filter(None, [explicit, os.environ.get("CHROME"), *CHROMES]):
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    sys.exit("Chrome or Chromium not found: pass --chrome PATH or set CHROME")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(source: Path, output: Path) -> None:
    """Store which source, in which version, the PDF in output/pdf/ was printed from."""
    entries = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    entries[output.name] = {"source": source.resolve().relative_to(ROOT).as_posix(),
                            "source_sha256": sha256(source), "pdf_sha256": sha256(output)}
    RECORD.write_text(json.dumps(dict(sorted(entries.items())), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--chrome")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html(args.source), encoding="utf-8")
        subprocess.run([chrome(args.chrome), "--headless", "--no-sandbox", "--disable-gpu",
                        "--no-pdf-header-footer", f"--print-to-pdf={args.output.resolve()}", page.as_uri()],
                       check=True, capture_output=True)
    if args.output.resolve().parent == RECORD.parent:
        record(args.source, args.output)
    print(f"{args.output}: {args.output.stat().st_size} B")


if __name__ == "__main__":
    main()
