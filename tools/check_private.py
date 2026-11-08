# SPDX-License-Identifier: MIT
"""Block private foundation material from the public repository (CONTRIBUTING.md, "Materiały prywatne").

Usage:
  python3 tools/check_private.py --staged           pre-commit hook: staged changes
  python3 tools/check_private.py --message FILE     commit-msg hook: the commit message
  python3 tools/check_private.py --pre-push         pre-push hook: refs on standard input
  python3 tools/check_private.py --range BASE HEAD  CI and by hand: every commit in BASE..HEAD
  python3 tools/check_private.py --text-env NAME..  CI: texts in environment variables (PR title, body)
Add --show to print the matching private item; use it only in your own terminal.

Private lists come from the foundation checkout: $WICI_FUNDACJA, by default the folder `fundacja`
next to this repository. Without it (CI, cloud sessions) only the general rules run.
Rules:
  P1 copy of a foundation file (SHA-256)     P2 e-mail or phone found in foundation texts
  P3 phrase from fundacja/.straznik/frazy.txt
  G1 IBAN   G2 PESEL (with the word "PESEL")   G3 phone number (with +48 or "tel")
  G4 e-mail outside the allowlist
  S1 forbidden path (fundacja/, _inbox/, .straznik/, *prywat*)
A hit names the place in this repository and the rule, never the private item itself.
Each commit is checked on its own: text added and removed again in a later commit is still in history.
"""

from fnmatch import fnmatch
from pathlib import Path
import hashlib
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOW_FILE = ROOT / "tools" / "check_private_allow.txt"
ZERO = "0" * 40
MIN_HASHED = 64  # smaller files (empty, a line of text) would match by chance
LONG_LINE = 400  # minified or generated lines: general rules skip them
TEXT_SUFFIXES = {".md", ".txt", ".html", ".htm", ".csv", ".json", ".eml", ".tex", ".yml", ".yaml"}
TRAILER = re.compile(r"^(Signed-off-by|Co-Authored-By|Reviewed-by|Acked-by):", re.IGNORECASE)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w+])(\+48[ -]?)?(\d{3}[ -]\d{3}[ -]\d{3}|\d{2}[ -]\d{3}[ -]\d{2}[ -]\d{2})(?!\w)")
PHONE_CONTEXT = re.compile(r"(tel\.?|telefon\w*|kom\.?|komórk\w*|phone|mobile)\s*:?\s*$", re.IGNORECASE)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")


def git(*args: str) -> bytes:
    """Git in the current directory: the repository being committed to or pushed from."""
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def phone_digits(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    return digits[2:] if len(digits) == 11 and digits.startswith("48") else digits


def iban_valid(text: str) -> bool:
    value = text.replace(" ", "")
    if not 15 <= len(value) <= 34:
        return False
    moved = value[4:] + value[:4]
    return int("".join(str(int(ch, 36)) for ch in moved)) % 97 == 1


def pesel_valid(text: str) -> bool:
    d = [int(ch) for ch in text]
    if (10 - sum(w * x for w, x in zip((1, 3, 7, 9, 1, 3, 7, 9, 1, 3), d)) % 10) % 10 != d[10]:
        return False
    month, day = (d[2] * 10 + d[3]) % 20, d[4] * 10 + d[5]
    return 1 <= month <= 12 and 1 <= day <= 31


def read_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line.casefold() for line in lines if line and not line.startswith("#")]


def find_foundation() -> Path | None:
    if os.environ.get("WICI_FUNDACJA"):
        path = Path(os.environ["WICI_FUNDACJA"]).expanduser()
        return path if path.is_dir() else None
    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
    except subprocess.CalledProcessError:
        return None
    path = Path(common).parent.parent / "fundacja"
    return path if path.is_dir() else None


class Rules:
    def __init__(self, foundation: Path | None):
        self.allow = read_list(ALLOW_FILE)
        self.hashes: dict[str, int] = {}
        self.sizes: set[int] = set()
        self.contacts: dict[str, int] = {}
        self.phrases: list[str] = []
        if foundation is None:
            return
        self.allow += read_list(foundation / ".straznik" / "dozwolone.txt")
        self.phrases = read_list(foundation / ".straznik" / "frazy.txt")
        for path in sorted(foundation.rglob("*")):
            if ".git" in path.relative_to(foundation).parts or not path.is_file():
                continue
            data = path.read_bytes()
            if len(data) >= MIN_HASHED:
                self.hashes.setdefault(hashlib.sha256(data).hexdigest(), len(self.hashes) + 1)
                self.sizes.add(len(data))
            if path.suffix.lower() in TEXT_SUFFIXES:
                text = data.decode("utf-8", errors="ignore")
                for email in EMAIL.findall(text):
                    if not self.allowed(email):
                        self.contacts.setdefault(email.casefold(), len(self.contacts) + 1)
                for match in PHONE.finditer(text):
                    digits = phone_digits(match.group(0))
                    if not self.allowed(digits):
                        self.contacts.setdefault(digits, len(self.contacts) + 1)

    def allowed(self, item: str) -> bool:
        item = item.casefold()
        return any(fnmatch(item, pattern) for pattern in self.allow)

    def line(self, text: str) -> list[tuple[str, str]]:
        """Hits in one added line as (rule, private item)."""
        hits = []
        folded = text.casefold()
        for number, phrase in enumerate(self.phrases, 1):
            if phrase in folded:
                hits.append((f"P3 #{number}", phrase))
        for email in EMAIL.findall(text):
            key = email.casefold()
            if key in self.contacts:
                hits.append((f"P2 #{self.contacts[key]}", email))
            elif not self.allowed(key) and len(text) <= LONG_LINE and not TRAILER.match(text.strip()):
                hits.append(("G4", email))
        for match in PHONE.finditer(text):
            digits = phone_digits(match.group(0))
            if digits in self.contacts:
                hits.append((f"P2 #{self.contacts[digits]}", match.group(0)))
            elif (len(text) <= LONG_LINE and not self.allowed(digits)
                  and (match.group(1) or PHONE_CONTEXT.search(text[:match.start()]))):
                hits.append(("G3", match.group(0)))
        if len(text) <= LONG_LINE:
            hits += [("G1", m) for m in IBAN.findall(text) if iban_valid(m)]
            # 11-digit part numbers (e.g. Würth pin headers) pass the PESEL checksum: the word must be on the line.
            if "pesel" in folded:
                hits += [("G2", m) for m in PESEL.findall(text) if pesel_valid(m)]
        return hits

    def blob(self, data: bytes) -> str | None:
        if len(data) not in self.sizes:
            return None
        number = self.hashes.get(hashlib.sha256(data).hexdigest())
        return f"P1 #{number}" if number else None


def forbidden_path(path: str) -> bool:
    parts = [part.casefold() for part in path.split("/")]
    return any(part in {"fundacja", "_inbox", ".straznik"} or "prywat" in part for part in parts)


def check_text(rules: Rules, place: str, text: str, out: list[str], show: bool) -> None:
    for number, line in enumerate(text.splitlines(), 1):
        for rule, item in rules.line(line):
            out.append(f"{place}:{number}: {rule}" + (f" [{item}]" if show else ""))


def check_diff(rules: Rules, where: str, diff_args: list[str], out: list[str], show: bool) -> None:
    """Paths, blobs and added lines of one diff (`git diff` or `git diff-tree` arguments)."""
    raw = git(*diff_args, "--raw", "-z", "--no-abbrev", "--diff-filter=ACMR").split(b"\0")
    i = 0
    while i < len(raw) - 1:
        meta = raw[i].decode()
        if not meta.startswith(":"):
            i += 1
            continue
        fields = meta[1:].split()
        status, new_sha = fields[4], fields[3]
        path = raw[i + 2 if status[0] in "RC" else i + 1].decode("utf-8", errors="replace")
        i += 3 if status[0] in "RC" else 2
        if forbidden_path(path):
            out.append(f"{where}{path}: S1" + (f" [{path}]" if show else ""))
        if new_sha != ZERO and int(git("cat-file", "-s", new_sha)) in rules.sizes:
            rule = rules.blob(git("cat-file", "blob", new_sha))
            if rule:
                out.append(f"{where}{path}: {rule}")
    patch = git(*diff_args, "-p", "-U0", "--no-color", "--no-ext-diff", "--diff-filter=ACMR").decode("utf-8", "replace")
    path, line_no, previous = "?", 0, ""
    for line in patch.splitlines():
        header, previous = previous.startswith("--- ") and line.startswith("+++ "), line
        if header:
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            line_no = int(re.search(r"\+(\d+)", line).group(1))
        elif line.startswith("+"):
            for rule, item in rules.line(line[1:]):
                out.append(f"{where}{path}:{line_no}: {rule}" + (f" [{item}]" if show else ""))
            line_no += 1


def check_commits(rules: Rules, commits: list[str], out: list[str], show: bool) -> None:
    for sha in commits:
        where = f"{sha[:12]} "
        check_diff(rules, where, ["diff-tree", "-r", "--root", "-m", "--first-parent", sha], out, show)
        check_text(rules, f"{where}(commit message)", git("log", "-1", "--format=%B", sha).decode(), out, show)


def main(argv: list[str]) -> int:
    show = "--show" in argv
    args = [a for a in argv if a != "--show"]
    if not args or args[0] not in {"--staged", "--message", "--pre-push", "--range", "--text-env"}:
        print(__doc__.split("\n\n")[1])
        return 2
    foundation = find_foundation()
    rules = Rules(foundation)
    if foundation is None:
        print("check_private: foundation lists not found, general rules only", file=sys.stderr)
    out: list[str] = []
    mode = args[0]
    if mode == "--staged":
        check_diff(rules, "", ["diff", "--cached"], out, show)
    elif mode == "--message":
        text = Path(args[1]).read_text(encoding="utf-8", errors="replace")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        check_text(rules, "(commit message)", text, out, show)
    elif mode == "--pre-push":
        commits: list[str] = []
        for line in sys.stdin.read().splitlines():
            local_sha = line.split()[1] if len(line.split()) == 4 else ZERO
            if local_sha != ZERO:
                listed = git("rev-list", local_sha, "--not", "--remotes").decode().split()
                commits += [c for c in listed if c not in commits]
        check_commits(rules, commits, out, show)
    elif mode == "--range":
        check_commits(rules, git("rev-list", f"{args[1]}..{args[2]}").decode().split(), out, show)
    else:
        for name in args[1:]:
            check_text(rules, f"${name}", os.environ.get(name, ""), out, show)
    for hit in out:
        print(f"private material? {hit}")
    if out:
        print("Blocked: this looks like private foundation material (rules in tools/check_private.py).\n"
              "Remove it, or add a public item to tools/check_private_allow.txt. "
              "Details: python3 tools/check_private.py ... --show (in your own terminal).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
