# SPDX-License-Identifier: MIT
"""Read-only publication checks: hashes, links, syntax and calculation results."""

from pathlib import Path
import ast
import hashlib
import html
import json
import re
import argparse
import sys
from urllib.parse import unquote

from release import published_files

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERNS = {".md": r"\[[^\]]*\]\(([^)]+)\)", ".html": r'(?:href|src)="([^"]+)"'}


def markdown_anchors(path: Path) -> set[str]:
    """Anchors GitHub makes from Markdown headings (lower case, punctuation dropped, spaces to "-",
    repeats numbered), plus explicit <a id> / <a name>; headings inside code blocks do not count."""
    anchors, seen, fenced = set(), {}, False
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        heading = None if fenced else re.match(r"#{1,6}\s+(.*)", line)
        if heading:
            slug = re.sub(r"<[^>]+>", "", heading.group(1).replace("`", "").strip().lower())
            slug = re.sub(r"[^\w\- ]", "", slug).replace(" ", "-")
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors | set(re.findall(r'<a (?:id|name)="([^"]+)"', text))


def check_links(path: Path, name: str) -> int:
    """Count local links of a Markdown or HTML document; reject missing files and missing anchors."""
    text = path.read_text(encoding="utf-8")
    count = 0
    for match in re.finditer(LINK_PATTERNS[path.suffix], text):
        raw = html.unescape(match.group(1)) if path.suffix == ".html" else match.group(1)
        target, _, fragment = raw.partition("#")
        if re.match(r"[a-z]+:", target):
            continue
        linked = path.parent / unquote(target) if target else path
        if not target and linked.suffix not in (".html", ".md"):
            continue
        if not linked.is_file():
            raise ValueError(f"Broken document link in {name}: {raw}")
        if fragment and linked.suffix == ".html" and f'id="{fragment}"' not in linked.read_text(encoding="utf-8"):
            raise ValueError(f"Missing document anchor in {name}: {raw}")
        if fragment and linked.suffix == ".md" and unquote(fragment).lower() not in markdown_anchors(linked):
            raise ValueError(f"Missing document anchor in {name}: {raw}")
        count += 1
    return count


def check_printed_pdfs(root: Path = ROOT) -> int:
    """Reject a PDF in output/pdf/ whose Markdown source changed after printing (tools/doc_pdf.py)."""
    record = root / "output/pdf/zrodla.json"
    entries = json.loads(record.read_text(encoding="utf-8"))
    for pdf, entry in entries.items():
        for path, key in ((root / entry["source"], "source_sha256"), (record.parent / pdf, "pdf_sha256")):
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry[key]:
                raise ValueError(f"Printed PDF output/pdf/{pdf} is stale: print it again from {entry['source']} "
                                 "with tools/doc_pdf.py")
    return len(entries)


def main() -> None:
    """Reject stale evidence or broken local documentation without refreshing it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull-request", action="store_true",
                        help="Accepted for older instructions; the check is the same with or without it")
    parser.parse_args()
    files = published_files()
    links = 0
    for name, path in files.items():
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=name)
        if path.suffix in (".md", ".html", ".css", ".py", ".json", ".dsn", ".xml", ".txt", ".log"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"https://chatgpt\.com/(?:space/)?page_|page_[0-9a-f]{16,}|/(?:Users|private/tmp)/", text):
                raise ValueError(f"Private export metadata or absolute scratch path: {name}")
        if path.suffix in LINK_PATTERNS:
            links += check_links(path, name)
    sys.path.insert(0, str(ROOT / "software/reference"))
    from obliczenia import calculate
    if calculate() != json.loads((ROOT / "software/reference/wyniki.json").read_text(encoding="utf-8")):
        raise ValueError("Stored calculation results are stale")
    record = json.loads((ROOT / "software/reference/weryfikacja.json").read_text(encoding="utf-8"))
    for name, digest in record["source_hashes"].items():
        if hashlib.sha256((ROOT / "software/reference" / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Reference verification evidence is stale: {name}")
    printed = check_printed_pdfs()
    print(f"Repository checks passed; {links} local links, {printed} printed PDFs")


if __name__ == "__main__":
    main()
