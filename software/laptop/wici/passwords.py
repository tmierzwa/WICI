# SPDX-License-Identifier: MIT
"""Envelope passwords: words drawn at random from slowa.txt (docs/spec/oprogramowanie.md).

4096 words without Polish letters, so every word carries 12 bits and types on any keyboard layout:
an account password of 5 words has 60 bits, the recovery password of 6 words 72 bits. The list and
how it is built are in software/laptop/build/slowa/; it is CC-BY-SA-4.0 (SJP.PL, FrequencyWords).
"""

import re
import secrets
from importlib import resources

SIZE = 4096
ACCOUNT_WORDS, RECOVERY_WORDS = 5, 6
_words = None


def words():
    global _words
    if _words is None:
        found = resources.files("wici").joinpath("slowa.txt").read_text(encoding="utf-8").split()
        if len(found) != SIZE or len(set(found)) != SIZE or not all(re.fullmatch(r"[abcdefghijklmnoprstuwyz]{3,7}", w) for w in found):
            raise ValueError("slowa.txt: lista słów uszkodzona")
        _words = found
    return _words


def generate(count=ACCOUNT_WORDS):
    return " ".join(secrets.choice(words()) for _ in range(count))


def recovery():
    return generate(RECOVERY_WORDS)
