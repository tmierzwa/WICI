# SPDX-License-Identifier: MIT
"""DCO check of pull request commits (tools/check_dco.py) on a throwaway Git repository."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_dco  # noqa: E402


def git(repo: Path, *args: str) -> str:
    # PATH from the caller (Homebrew, Nix); user and system Git config ignored (signing, hooks, default branch).
    env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="T",
               GIT_COMMITTER_EMAIL="t@example.org", HOME=str(repo), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env).stdout.strip()


class CheckDco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, message: str) -> None:
        git(self.repo, "commit", "-q", "--allow-empty", "-m", message)

    def test_signed_commits_pass(self):
        self.commit("one\n\nSigned-off-by: Tomek Mierzwa <tm@example.org>")
        self.commit("two\n\nCo-Authored-By: X <x@example.org>\nSigned-off-by: A B <a@example.org>")
        self.assertEqual(check_dco.unsigned(self.base, "HEAD", self.repo), [])

    def test_unsigned_or_malformed_commits_fail(self):
        self.commit("good\n\nSigned-off-by: A B <a@example.org>")
        self.commit("missing")
        self.commit("no email\n\nSigned-off-by: A B")
        self.commit("in text: Signed-off-by: A B <a@example.org> is not a trailer line")
        subjects = [line.split(" ", 1)[1] for line in check_dco.unsigned(self.base, "HEAD", self.repo)]
        self.assertEqual(subjects, ["in text: Signed-off-by: A B <a@example.org> is not a trailer line", "no email", "missing"])

    def test_merge_commits_are_skipped(self):
        git(self.repo, "checkout", "-q", "-b", "side")
        self.commit("side\n\nSigned-off-by: A B <a@example.org>")
        git(self.repo, "checkout", "-q", "main")
        self.commit("main\n\nSigned-off-by: A B <a@example.org>")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "Merge side", "side")
        self.assertEqual(check_dco.unsigned(self.base, "HEAD", self.repo), [])


if __name__ == "__main__":
    unittest.main()
