# SPDX-License-Identifier: MIT
"""List published files and build a source-only ZIP with its manifest for a release.

The manifest (SHA-256 of every published file) is not kept in the repository: Git guards the files between
releases, and the manifest is made only for a release, inside the ZIP and next to it.
"""

from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

from archives import validate_names, verify_archive, write_archive

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SKIP = ("media/film/", ".mp4")  # rendered films stay in Git and on Pages; their sources go in the ZIP
MANIFEST = "manifest.json"


def sha(path: Path) -> str:
    """Hash exact published bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_files() -> set[str]:
    """Use the Git index as the publication boundary, never all local files."""
    output = subprocess.check_output(["git", "ls-files", "-z", "--cached"], cwd=ROOT)
    names = set(output.decode().rstrip("\0").split("\0"))
    validate_names(list(names))
    for name in names:
        parts = Path(name).parts
        if "reference-private" in parts or ".venv" in parts or "dist" in parts or "__pycache__" in parts:
            raise ValueError(f"Private or generated local file staged: {name}")
        if (ROOT / name).is_symlink():
            raise ValueError(f"Publication source is a symlink: {name}")
        if name == MANIFEST:
            raise ValueError("manifest.json is made for a release only; remove it from the Git index")
    return names


def published_files() -> dict[str, Path]:
    """Every file in the Git index, by repository path."""
    return {name: ROOT / name for name in sorted(tracked_files())}


def archive_files(files: dict[str, Path]) -> dict[str, Path]:
    """Leave rendered videos out of the source ZIP; everything needed to rebuild them stays in."""
    folder, suffix = ARCHIVE_SKIP
    return {name: path for name, path in files.items() if not (name.startswith(folder) and name.endswith(suffix))}


def manifest(version: str, files: dict[str, Path]) -> str:
    """Release manifest: project, version and the SHA-256 of every file in the archive."""
    data = {"format": 3, "project": "WICI", "version": version,
            "files": {name: sha(path) for name, path in sorted(files.items())}}
    return json.dumps(data, indent=2) + "\n"


def build_release(version: str, target: Path) -> Path:
    """Write the source ZIP (with manifest.json inside) and the same manifest next to it."""
    if not re.fullmatch(r"\d+\.\d+(\.\d+)?", version):
        raise ValueError(f"Release version must look like 0.6 or 0.6.1: {version}")
    files = published_files()
    target = target.resolve()
    if target in {path.resolve() for path in files.values()}:
        raise ValueError("Archive destination would overwrite published source")
    source = archive_files(files)
    text = manifest(version, source)
    with tempfile.TemporaryDirectory() as temp:
        listed = Path(temp) / MANIFEST
        listed.write_text(text, encoding="utf-8")
        write_archive(target, {**source, MANIFEST: listed})
        verify_archive(target, {**source, MANIFEST: listed})
    beside = target.with_name(target.name.removesuffix(".zip") + "-manifest.json")
    beside.write_text(text, encoding="utf-8")
    return beside


def main() -> None:
    """Without arguments list the published files; with --version and --source-zip build a release archive."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="Release number without the v, e.g. 0.6")
    parser.add_argument("--source-zip", type=Path, help="Build a source archive, not a bootable USB image")
    args = parser.parse_args()
    if bool(args.version) != bool(args.source_zip):
        parser.error("--version and --source-zip go together")
    files = published_files()
    if args.source_zip:
        beside = build_release(args.version, args.source_zip)
        print(f"Source archive {args.source_zip} and {beside.name}: {len(archive_files(files))} files")
    else:
        print(f"Published files: {len(files)}")


if __name__ == "__main__":
    main()
