# SPDX-License-Identifier: MIT
"""Reject pull request commits without a DCO sign-off (CONTRIBUTING.md, "Pochodzenie wkładu (DCO)").

Usage: python3 tools/check_dco.py <base> <head>
Every non-merge commit in base..head must carry a trailer line
"Signed-off-by: Name <email>". Merge commits made by GitHub ("Update branch") are skipped.
"""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SIGN_OFF = re.compile(r"^Signed-off-by: \S.* <[^<>@\s]+@[^<>@\s]+>\s*$", re.MULTILINE)


def unsigned(base: str, head: str, repo: Path = ROOT) -> list[str]:
    """Commits in base..head (without merges) whose message has no sign-off, as "sha subject"."""
    log = subprocess.run(["git", "log", "--no-merges", "--format=%H%x00%s%x00%B%x1e", f"{base}..{head}"],
                         cwd=repo, capture_output=True, text=True, check=True).stdout
    missing = []
    for entry in filter(None, (part.strip("\n") for part in log.split("\x1e"))):
        sha, subject, body = entry.split("\x00", 2)
        if not SIGN_OFF.search(body):
            missing.append(f"{sha[:12]} {subject}")
    return missing


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.splitlines()[2])
        return 2
    missing = unsigned(sys.argv[1], sys.argv[2])
    for line in missing:
        print(f"missing Signed-off-by: {line}")
    if missing:
        print("Sign off each commit (git commit -s; existing commits: git rebase --signoff <base>).")
        return 1
    print("DCO: every commit is signed off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
