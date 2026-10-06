# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and compare archives against an explicit, nonempty file set."""

from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def validate_names(names: list[str]) -> None:
    """Reject empty, duplicate or nonportable archive paths."""
    if not names or len(set(names)) != len(names):
        raise ValueError("Archive must contain a nonempty set of unique files")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name or name.endswith("/"):
            raise ValueError(f"Invalid archive path: {name}")


def verify_archive(archive: Path, files: dict[str, Path]) -> None:
    """Require exact membership and byte equality with the source files."""
    validate_names(list(files))
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        validate_names(names)
        if set(names) != set(files):
            raise ValueError(f"Archive membership mismatch: {archive.name}")
        for name, source in files.items():
            if bundle.read(name) != source.read_bytes():
                raise ValueError(f"Stale archive member: {name}")


def write_archive(archive: Path, files: dict[str, Path]) -> None:
    """Write a ZIP with stable order, timestamps and file permissions."""
    validate_names(list(files))
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, source in sorted(files.items()):
                info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, source.read_bytes(), compresslevel=9)
        verify_archive(temporary, files)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
