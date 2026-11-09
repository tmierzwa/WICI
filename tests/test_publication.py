# SPDX-License-Identifier: MIT
"""Regression cases for invalid source archives and read-only checks."""

from pathlib import Path
import hashlib
import json
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
from verify_repository import check_links, check_printed_pdfs
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
    """Reject broken local links and anchors in HTML and Markdown documents."""

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

    def test_markdown_anchors_follow_github_headings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "b.md"
            target.write_text("# Próby według kroków\n## Krok 2: radia `RNode`\n## Krok 2: radia `RNode`\n"
                              "```\n# nie nagłówek\n```\n<a id=\"recznie\"></a>\n", encoding="utf-8")
            page = root / "a.md"
            page.write_text("## Wstęp\n[a](b.md#próby-według-kroków) [b](b.md#krok-2-radia-rnode-1) "
                            "[c](b.md#recznie) [d](#wstęp) [e](b.md#Pr%C3%B3by-wed%C5%82ug-krok%C3%B3w)",
                            encoding="utf-8")
            self.assertEqual(check_links(page, "a.md"), 5)
            for broken in ("[x](b.md#nie-nagłówek)", "[x](b.md#krok-2-radia-rnode-2)", "[x](#brak)"):
                page.write_text(broken, encoding="utf-8")
                with self.assertRaises(ValueError):
                    check_links(page, "a.md")


class PrintedPdfTests(unittest.TestCase):
    """A PDF in output/pdf/ must come from the current version of its Markdown source."""

    def test_stale_source_or_replaced_pdf_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "output/pdf").mkdir(parents=True)
            source, pdf = root / "doc.md", root / "output/pdf/doc.pdf"
            source.write_text("# Instrukcja", encoding="utf-8")
            pdf.write_bytes(b"%PDF-1.4 print")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            (root / "output/pdf/zrodla.json").write_text(json.dumps({"doc.pdf": {
                "source": "doc.md", "source_sha256": digest(source), "pdf_sha256": digest(pdf)}}), encoding="utf-8")
            self.assertEqual(check_printed_pdfs(root), 1)
            source.write_text("# Instrukcja po poprawkach", encoding="utf-8")
            with self.assertRaises(ValueError):
                check_printed_pdfs(root)
            source.write_text("# Instrukcja", encoding="utf-8")
            pdf.write_bytes(b"%PDF-1.4 other print")
            with self.assertRaises(ValueError):
                check_printed_pdfs(root)


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


class ReleaseTests(unittest.TestCase):
    """The manifest exists only for a release: inside the source ZIP and next to it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "a.md").write_text("tekst", encoding="utf-8")
        (self.root / "media/film").mkdir(parents=True)
        (self.root / "media/film/film.mp4").write_bytes(b"video")
        subprocess.run(["git", "add", "a.md", "media/film/film.mp4"], cwd=self.root, check=True)
        old = release.ROOT
        release.ROOT = self.root
        self.addCleanup(setattr, release, "ROOT", old)

    def test_archive_carries_manifest_of_its_files(self):
        target = Path(self.temp.name) / "dist/WICI-0.6-source.zip"
        beside = release.build_release("0.6", target)
        self.assertEqual(beside.name, "WICI-0.6-source-manifest.json")
        data = json.loads(beside.read_text(encoding="utf-8"))
        self.assertEqual((data["project"], data["version"]), ("WICI", "0.6"))
        self.assertEqual(data["files"], {"a.md": hashlib.sha256(b"tekst").hexdigest()})
        with ZipFile(target) as bundle:
            self.assertEqual(set(bundle.namelist()), {"a.md", "manifest.json"})
            self.assertEqual(bundle.read("manifest.json").decode("utf-8"), beside.read_text(encoding="utf-8"))

    def test_manifest_in_index_or_bad_version_rejected(self):
        with self.assertRaises(ValueError):
            release.build_release("v0.6", Path(self.temp.name) / "x.zip")
        (self.root / "manifest.json").write_text("{}", encoding="utf-8")
        subprocess.run(["git", "add", "manifest.json"], cwd=self.root, check=True)
        with self.assertRaises(ValueError):
            release.published_files()


if __name__ == "__main__":
    unittest.main()
