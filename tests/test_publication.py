# SPDX-License-Identifier: MIT
"""Regression cases for invalid source archives and read-only checks."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.archives import verify_archive, write_archive

sys.path.insert(0, str(ROOT / "tools"))
from verify_repository import check_links
from build_pages import build
import release


class ArchiveTests(unittest.TestCase):
    """Exercise incomplete, stale and ambiguous distributions."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "design.txt"
        self.source.write_bytes(b"reviewed geometry")
        self.files = {"design.txt": self.source}
        self.archive = self.root / "design.zip"

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


class DocumentLinkTests(unittest.TestCase):
    """Reject broken local links and anchors in HTML documents."""

    def test_html_links_and_anchors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "b.html"
            target.write_text('<h2 id="x">X</h2>', encoding="utf-8")
            page = root / "a.html"
            page.write_text('<a href="b.html#x">b</a> <a href="https://example.org/">e</a> '
                            '<a href="mailto:a@example.org">m</a> <link href="b.html">', encoding="utf-8")
            self.assertEqual(check_links(page, "a.html"), 2)
            for broken in ('<a href="b.html#y">b</a>', '<a href="c.html">c</a>', '<a href="#y">self</a>'):
                page.write_text(broken, encoding="utf-8")
                with self.assertRaises(ValueError):
                    check_links(page, "a.html")


class PagesTests(unittest.TestCase):
    """Keep links between pages relative and point other links at repository files."""

    def test_links_leaving_pages_use_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "docs/pages"
            source.mkdir(parents=True)
            (root / "LICENSE.md").write_text("x", encoding="utf-8")
            (source / "style.css").write_text("", encoding="utf-8")
            (source / "a.html").write_text('<a href="b.html#x">b</a><a href="../../LICENSE.md#l">l</a>'
                                           '<a href="https://example.org/">e</a><a href="#top">t</a>', encoding="utf-8")
            site = root / "site"
            self.assertEqual(build(site, "https://repo/blob/abc/", source, root), 1)
            self.assertEqual((site / "a.html").read_text(encoding="utf-8"),
                             '<a href="b.html#x">b</a><a href="https://repo/blob/abc/LICENSE.md#l">l</a>'
                             '<a href="https://example.org/">e</a><a href="#top">t</a>')
            self.assertTrue((site / "style.css").is_file() and (site / ".nojekyll").is_file())
            (root / "film.mp4").write_bytes(b"video")
            (source / "a.html").write_text('<video src="../../film.mp4" poster="../../film.mp4"></video>', encoding="utf-8")
            self.assertEqual(build(site, "https://repo/blob/abc", source, root), 0)
            self.assertEqual((site / "a.html").read_text(encoding="utf-8"),
                             '<video src="media/film.mp4" poster="media/film.mp4"></video>')
            self.assertEqual((site / "media/film.mp4").read_bytes(), b"video")
            (source / "a.html").write_text('<a href="../missing.md">m</a>', encoding="utf-8")
            with self.assertRaises(ValueError):
                build(site, "https://repo/blob/abc", source, root)


class SourceArchiveScopeTests(unittest.TestCase):
    """Rendered films are published in Git and on Pages, not in the source ZIP."""

    def test_rendered_films_skipped(self):
        files = {name: Path(name) for name in
                 ("media/film/WICI-film.mp4", "media/film/wici_film.py", "media/film/plakat.jpg", "docs/x.mp4")}
        self.assertEqual(set(release.archive_files(files)),
                         {"media/film/wici_film.py", "media/film/plakat.jpg", "docs/x.mp4"})


class ManifestModeTests(unittest.TestCase):
    """Pull requests skip manifest hashes; the full check still rejects them."""

    def test_pull_request_mode_tolerates_stale_manifest_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "a.md").write_text("new", encoding="utf-8")
            (root / "manifest.json").write_text(
                '{"format": 2, "project": "WICI", "version": "0.5-prototype-design", "board": "R02",'
                ' "files": {"a.md": "0"}}', encoding="utf-8")
            subprocess.run(["git", "add", "a.md", "manifest.json"], cwd=root, check=True)
            old = release.ROOT
            release.ROOT = root
            try:
                with self.assertRaises(ValueError):
                    release.check_manifest()
                self.assertEqual(set(release.check_manifest(strict=False)), {"a.md", "manifest.json"})
            finally:
                release.ROOT = old


if __name__ == "__main__":
    unittest.main()
