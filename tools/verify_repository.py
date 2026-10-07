# SPDX-License-Identifier: MIT
"""Read-only publication checks: hashes, links, syntax and calculation results."""

from pathlib import Path
import ast
import hashlib
import html
import json
import re
import argparse
import subprocess
import sys
from urllib.parse import unquote

from release import check_manifest

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERNS = {".md": r"\[[^\]]*\]\(([^)]+)\)", ".html": r'(?:href|src)="([^"]+)"'}


def check_links(path: Path, name: str) -> int:
    """Count local links of a Markdown or HTML document; reject missing files and HTML anchors."""
    text = path.read_text(encoding="utf-8")
    count = 0
    for match in re.finditer(LINK_PATTERNS[path.suffix], text):
        raw = html.unescape(match.group(1)) if path.suffix == ".html" else match.group(1)
        target, _, fragment = raw.partition("#")
        if re.match(r"[a-z]+:", target):
            continue
        linked = path.parent / unquote(target) if target else path
        if not target and linked.suffix != ".html":
            continue
        if not linked.is_file():
            raise ValueError(f"Broken document link in {name}: {raw}")
        if fragment and linked.suffix == ".html" and f'id="{fragment}"' not in linked.read_text(encoding="utf-8"):
            raise ValueError(f"Missing document anchor in {name}: {raw}")
        count += 1
    return count


def main() -> None:
    """Reject stale evidence or broken local documentation without refreshing it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull-request", action="store_true",
                        help="Do not require a refreshed manifest; the maintainer refreshes it")
    args = parser.parse_args()
    files = check_manifest(strict=not args.pull_request)
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
    subprocess.run([sys.executable, str(ROOT / "hardware/radio-test-r01/tools/check_bundle.py"), "--check"], check=True)
    print(f"Repository checks passed; {links} local links; hardware HOLD retained")


if __name__ == "__main__":
    main()
