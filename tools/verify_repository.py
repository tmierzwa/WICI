# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only publication checks: hashes, links, syntax and calculation results."""

from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote

from release import check_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Reject stale evidence or broken local documentation without refreshing it."""
    files = check_manifest()
    links = 0
    for name, path in files.items():
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=name)
        if path.suffix in (".md", ".py", ".json", ".dsn", ".xml", ".txt", ".log"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"https://chatgpt\.com/(?:space/)?page_|page_[0-9a-f]{16,}|/(?:Users|private/tmp)/", text):
                raise ValueError(f"Private export metadata or absolute scratch path: {name}")
        if path.suffix == ".md":
            for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                target = match.group(1).split("#", 1)[0]
                if not target or re.match(r"[a-z]+://", target):
                    continue
                if not (path.parent / unquote(target)).is_file():
                    raise ValueError(f"Broken document link in {name}: {target}")
                links += 1
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
