# SPDX-License-Identifier: MIT
"""Refresh or check the public source manifest and build a source-only ZIP."""

from pathlib import Path
import argparse
import hashlib
import json
import subprocess

from archives import validate_names, verify_archive, write_archive

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SKIP = ("media/film/", ".mp4")  # rendered films stay in Git and on Pages; their sources go in the ZIP


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
    return names


def check_manifest(strict: bool = True) -> dict[str, Path]:
    """Check every source hash and, in a checkout, the exact tracked file set.

    A non-strict check is for pull requests: contributors do not refresh the
    manifest, so the tracked files are checked without comparing their hashes.
    """
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["project"], manifest["version"], manifest["controller"]) != ("WICI", "0.4-prototype-design", "R01.3"):
        raise ValueError("Unexpected release identity")
    if not strict:
        return {name: ROOT / name for name in sorted(tracked_files())}
    files = {name: ROOT / name for name in manifest["files"]}
    validate_names(list(files))
    if "manifest.json" in files:
        raise ValueError("Manifest must not hash itself")
    if (ROOT / ".git").exists() and tracked_files() != set(files) | {"manifest.json"}:
        raise ValueError("Manifest and Git index file sets differ; review then refresh")
    for name, path in files.items():
        if path.is_symlink() or sha(path) != manifest["files"][name]:
            raise ValueError(f"Source checksum mismatch: {name}")
    return {**files, "manifest.json": ROOT / "manifest.json"}


def archive_files(files: dict[str, Path]) -> dict[str, Path]:
    """Leave rendered videos out of the source ZIP; everything needed to rebuild them stays in."""
    folder, suffix = ARCHIVE_SKIP
    return {name: path for name, path in files.items() if not (name.startswith(folder) and name.endswith(suffix))}


def main() -> None:
    """Check by default; only an explicit refresh rewrites the manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Hash reviewed files in the Git index")
    parser.add_argument("--source-zip", type=Path, help="Build a source archive, not a bootable USB image")
    args = parser.parse_args()
    if args.refresh:
        names = tracked_files() - {"manifest.json"}
        data = {"format": 2, "project": "WICI", "version": "0.4-prototype-design", "controller": "R01.3",
                "files": {name: sha(ROOT / name) for name in sorted(names)}}
        (ROOT / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    files = check_manifest()
    if args.source_zip:
        target = args.source_zip.resolve()
        if target in {p.resolve() for p in files.values()}:
            raise ValueError("Archive destination would overwrite published source")
        source = archive_files(files)
        write_archive(target, source)
        verify_archive(target, source)
    print(f"Public source checked: {len(files)} files")


if __name__ == "__main__":
    main()
