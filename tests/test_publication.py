# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression cases for invalid controller archives and read-only checks."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.archives import verify_archive, write_archive


class ArchiveTests(unittest.TestCase):
    """Exercise incomplete, stale and ambiguous distributions."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "design.txt"
        self.source.write_bytes(b"reviewed geometry")
        self.files = {"design.txt": self.source}
        self.archive = self.root / "controller.zip"

    def test_empty_zip_rejected(self):
        with ZipFile(self.archive, "w"):
            pass
        with self.assertRaises(ValueError):
            verify_archive(self.archive, self.files)

    def test_missing_or_extra_member_rejected(self):
        for content in ({"wrong.txt": b"x"}, {"design.txt": self.source.read_bytes(), "private.txt": b"x"}):
            with ZipFile(self.archive, "w") as bundle:
                for name, data in content.items():
                    bundle.writestr(name, data)
            with self.assertRaises(ValueError):
                verify_archive(self.archive, self.files)

    def test_stale_member_rejected(self):
        write_archive(self.archive, self.files)
        self.source.write_bytes(b"new geometry")
        with self.assertRaises(ValueError):
            verify_archive(self.archive, self.files)

    def test_duplicate_or_unsafe_member_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(self.archive, "w") as bundle:
                bundle.writestr("design.txt", self.source.read_bytes())
                bundle.writestr("design.txt", self.source.read_bytes())
        with self.assertRaises(ValueError):
            verify_archive(self.archive, self.files)
        for name in ("../private.txt", "/absolute.txt", "back\\slash.txt"):
            with self.assertRaises(ValueError):
                write_archive(self.archive, {name: self.source})

    def test_stable_archive_and_roundtrip(self):
        write_archive(self.archive, self.files)
        first = self.archive.read_bytes()
        write_archive(self.archive, self.files)
        self.assertEqual(first, self.archive.read_bytes())
        verify_archive(self.archive, self.files)

    def test_controller_gate_rejects_empty_zip_without_rewriting(self):
        project = self.root / "project"
        hardware = project / "hardware/radio-test-r01"
        shutil.copytree(ROOT / "hardware/radio-test-r01", hardware,
                        ignore=shutil.ignore_patterns("reference-private", "__pycache__", "*.kicad_prl"))
        shutil.copytree(ROOT / "tools", project / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        status = hardware / "checks/status.json"
        manifest = hardware / "manifest.sha256.json"
        before = (status.read_bytes(), manifest.read_bytes())
        with ZipFile(hardware / "fabrication/wici-controller-R01.3.zip", "w"):
            pass
        for options in ([], ["-O"]):
            result = subprocess.run([sys.executable, *options, str(hardware / "tools/check_bundle.py"), "--check"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("Archive must contain", result.stderr)
            self.assertEqual(before, (status.read_bytes(), manifest.read_bytes()))


if __name__ == "__main__":
    unittest.main()
