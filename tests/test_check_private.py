# SPDX-License-Identifier: MIT
"""Private material check (tools/check_private.py) on a throwaway repository and foundation folder.

Test values that look like personal data are joined from pieces at run time, so this file itself
passes the check it tests.
"""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_private.py"
NAME = "Jan Przykładowski"
SECRET_NOTE = f"Notatka ze spotkania z darczyńcą: {NAME} z Fundacji Testowej Alfa.\n" * 3
CONTACT_EMAIL = "jan.p" "@redakcja-testowa.pl"
CONTACT_PHONE = "601 202" " 303"
FOUNDATION_ALLOWED = "biuro" "@wici-test.pl"
OTHER_EMAIL = "anna" "@gdzies.pl"
OTHER_PHONE = "512 345" " 678"
IBAN = "PL61 1090 1014" " 0000 0712 1981 2874"  # published sample IBAN with a valid checksum
BAD_IBAN = "PL61109010140000" "071219812875"
PESEL = "4405" "1401359"  # valid checksum and date
BAD_PESEL = "4405" "1401358"
PART_NUMBER = "6130" "0211121"  # Würth pin header: passes the PESEL checksum


class CheckPrivate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo, self.foundation = base / "repo", base / "fundacja"
        (self.foundation / ".straznik").mkdir(parents=True)
        (self.foundation / "notatka.md").write_text(f"{SECRET_NOTE}Kontakt: {CONTACT_EMAIL}, tel. {CONTACT_PHONE}\n",
                                                   encoding="utf-8")
        (self.foundation / ".straznik" / "frazy.txt").write_text(f"# komentarz\n\n{NAME}\n", encoding="utf-8")
        (self.foundation / ".straznik" / "dozwolone.txt").write_text(f"{FOUNDATION_ALLOWED}\n", encoding="utf-8")
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="T",
                        GIT_COMMITTER_EMAIL="t@example.org", HOME=str(base), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull, WICI_FUNDACJA=str(self.foundation))
        self.no_foundation = dict(self.env, WICI_FUNDACJA=str(base / "brak"))
        self.git("init", "-q", "-b", "main")
        self.commit("README.md", "start\n")
        self.base = self.git("rev-parse", "HEAD")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True,
                              env=self.env).stdout.strip()

    def commit(self, name: str, text: str | bytes, message: str = "change") -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
        self.git("add", name)
        self.git("commit", "-q", "-m", message)

    def check(self, *args: str, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, input=stdin, capture_output=True,
                              text=True, env=env or self.env)

    def assert_blocked(self, rule: str, *args: str, **kw) -> str:
        result = self.check(*args, **kw)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(rule, result.stdout)
        return result.stdout

    def test_clean_change_passes(self):
        self.commit("docs/a.md", "Zwykły opis stacji, kontakt@wici.net.pl, 113 € za 5 płytek.\n")
        self.assertEqual(self.check("--range", self.base, "HEAD").returncode, 0)

    def test_copied_foundation_file(self):
        self.commit("docs/kopia.md", (self.foundation / "notatka.md").read_bytes())
        self.assert_blocked("P1 #", "--range", self.base, "HEAD")

    def test_phrase_is_reported_without_the_phrase(self):
        self.commit("docs/a.md", f"Rozmawiałem z {NAME.lower()} o pilotażu.\n")
        out = self.assert_blocked("docs/a.md:1: P3 #1", "--range", self.base, "HEAD")
        self.assertNotIn(NAME.casefold(), out.casefold())
        self.assertIn(f"[{NAME.casefold()}]", self.check("--range", self.base, "HEAD", "--show").stdout)

    def test_contacts_from_foundation_texts(self):
        self.commit("docs/a.md", f"Pisz na {CONTACT_EMAIL}\n")
        self.assert_blocked("P2 #", "--range", self.base, "HEAD")
        self.commit("docs/b.md", f"Numer {CONTACT_PHONE.replace(' ', '-')} do redakcji\n")
        self.assert_blocked("docs/b.md:1: P2 #", "--range", self.base, "HEAD")

    def test_allowlisted_email_passes(self):
        self.commit("docs/a.md", f"Biuro: {FOUNDATION_ALLOWED}, autor: 123+x@users.noreply.github.com\n")
        self.assertEqual(self.check("--range", self.base, "HEAD").returncode, 0)

    def test_general_rules_without_foundation(self):
        for text, rule in ((f"Konto {IBAN}\n", "G1"), (f"PESEL {PESEL}\n", "G2"), (f"tel. {OTHER_PHONE}\n", "G3"),
                           (f"Napisz do {OTHER_EMAIL}\n", "G4")):
            with self.subTest(rule=rule):
                self.commit("docs/x.md", text)
                self.assert_blocked(rule, "--range", "HEAD~1", "HEAD", env=self.no_foundation)

    def test_general_rules_ignore_lookalikes(self):
        text = (f"PESEL {BAD_PESEL} (zła suma kontrolna)\nListwa Würth {PART_NUMBER} i 100 200 300 mAh,"
                f" ID {BAD_IBAN}.\nSigned-off-by: Ktoś <{OTHER_EMAIL}>\n" + "x" * 500 + f" {OTHER_EMAIL}\n")
        self.commit("docs/x.md", text)
        self.assertEqual(self.check("--range", self.base, "HEAD", env=self.no_foundation).returncode, 0)

    def test_forbidden_path(self):
        self.commit("fundacja/plan.md", "plan\n")
        self.assert_blocked("S1", "--range", self.base, "HEAD")

    def test_commit_message(self):
        self.commit("docs/a.md", "ok\n", message=f"Notatka po rozmowie, {NAME}")
        self.assert_blocked("(commit message):1: P3", "--range", self.base, "HEAD")
        msg = self.repo / "MSG"
        msg.write_text(f"Tytuł\n\n{NAME}\n# {NAME} w komentarzu git\n", encoding="utf-8")
        self.assert_blocked("(commit message):3: P3", "--message", str(msg))

    def test_removed_later_is_still_in_history(self):
        self.commit("docs/a.md", f"{NAME}\n")
        self.commit("docs/a.md", "czysto\n")
        self.assert_blocked("P3", "--range", self.base, "HEAD")

    def test_staged(self):
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "a.md").write_text(f"ok\n{NAME}\n", encoding="utf-8")
        self.git("add", "docs/a.md")
        self.assert_blocked("docs/a.md:2: P3", "--staged")

    def test_pre_push_checks_commits_not_on_remotes(self):
        self.commit("docs/a.md", f"{NAME}\n")
        head = self.git("rev-parse", "HEAD")
        line = f"refs/heads/x {head} refs/heads/x {'0' * 40}\n"
        self.assert_blocked("P3", "--pre-push", stdin=line)
        self.git("update-ref", "refs/remotes/origin/x", head)  # already public: nothing new to check
        self.assertEqual(self.check("--pre-push", stdin=line).returncode, 0)

    def test_text_env(self):
        env = dict(self.env, PR_BODY=f"Opis\nkontakt: {CONTACT_EMAIL}")
        self.assert_blocked("$PR_BODY:2: P2", "--text-env", "PR_TITLE", "PR_BODY", env=env)


if __name__ == "__main__":
    unittest.main()
