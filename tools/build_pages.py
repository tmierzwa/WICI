# SPDX-License-Identifier: MIT
"""Build the GitHub Pages site from docs/conception without changing the sources."""

from pathlib import Path
import argparse
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/conception"
LOCAL_LINK = re.compile(r'(href|src|poster)="([^"#:]+)(#[^"]*)?"')
MEDIA = {".mp4", ".webm", ".vtt", ".jpg", ".png"}  # served with the site so browsers can play them


def build(target: Path, blob: str, source: Path = SOURCE, root: Path = ROOT) -> int:
    """Copy the pages; point links that leave the conception at repository files. Return their count.

    Media files (video, subtitles, images) outside the pages are copied to media/ in the site instead.
    """
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    rewritten = 0

    def repository_link(match: re.Match) -> str:
        nonlocal rewritten
        linked = (source / match.group(2)).resolve()
        if linked.parent == source.resolve():
            return match.group(0)
        if not linked.is_file():
            raise ValueError(f"Broken document link: {match.group(2)}")
        if linked.suffix in MEDIA:
            (target / "media").mkdir(exist_ok=True)
            shutil.copyfile(linked, target / "media" / linked.name)
            return f'{match.group(1)}="media/{linked.name}{match.group(3) or ""}"'
        rewritten += 1
        return f'{match.group(1)}="{blob.rstrip("/")}/{linked.relative_to(root.resolve()).as_posix()}{match.group(3) or ""}"'

    for path in sorted(source.iterdir()):
        if path.suffix == ".html":
            text = LOCAL_LINK.sub(repository_link, path.read_text(encoding="utf-8"))
            (target / path.name).write_text(text, encoding="utf-8")
        elif path.suffix == ".css":
            shutil.copyfile(path, target / path.name)
    (target / ".nojekyll").write_bytes(b"")
    return rewritten


def main() -> None:
    """Write the static site to the given directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--blob", required=True, help="Base URL of repository files, e.g. .../blob/<commit>")
    args = parser.parse_args()
    print(f"Pages built: {build(args.target.resolve(), args.blob)} links to repository files")


if __name__ == "__main__":
    main()
