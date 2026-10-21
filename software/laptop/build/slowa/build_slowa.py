# SPDX-License-Identifier: MIT
"""Build the word list for envelope passwords: software/laptop/wici/slowa.txt (docs/spec/oprogramowanie.md).

    python3 software/laptop/build/slowa/build_slowa.py [--check] [--candidates N] [--sjp]

4096 words, so a password of 5 words carries 60 bits and the recovery password of 6 words 72 bits.
A word is the base form of an entry of the SJP.PL inflection dictionary, 3 to 7 letters, without
Polish letters (the laptop is any laptop brought on the spot, often without a Polish keyboard
layout) and without q, v, x (outside the Polish alphabet, only in loanwords), not among the
20 000 most frequent English words and not excluded in wykluczone.txt (vulgar, offensive, death and
violence, names, rare or odd words). Words are ranked by how often the base form itself appears in
Polish film subtitles (FrequencyWords, OpenSubtitles 2018); the 4096 most frequent remain, in
alphabetical order. The sources are pinned in zrodla.json with SHA-256 and cached in
software/laptop/build/cache (build_usb.fetch). The result is CC-BY-SA-4.0 (FrequencyWords is ShareAlike).

SJP.PL removes the previous release when it publishes a new one, so the base forms that can enter the
list (3 to 7 letters, no Polish letters) are kept in sjp-lematy.txt (CC-BY-4.0); --sjp rebuilds that
file from the pinned release while it is still available. FrequencyWords is pinned to a Git commit.

--check rebuilds the list and fails if it differs from the file in the repository.
--candidates N prints the N most frequent words left after the filters, for reviewing exclusions.
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from build_usb import fetch as fetch_pinned  # noqa: E402  (pobieranie z sumą SHA-256 i pamięcią podręczną)

OUT = HERE.parents[1] / "wici" / "slowa.txt"
LEMMAS = HERE / "sjp-lematy.txt"
SOURCES = json.loads((HERE / "zrodla.json").read_text(encoding="utf-8"))
SIZE = 4096
WORD = re.compile(r"^[abcdefghijklmnoprstuwyz]{3,7}$")   # bez polskich liter i bez q, v, x
ENGLISH_TOP = 20_000
MIN_COUNT = 20                                           # wystąpienia form w napisach


def fetch(name):
    return fetch_pinned(SOURCES[name], name).read_bytes()


def frequencies(data):
    counts = {}
    for line in data.decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            counts[parts[0]] = int(parts[1])
    return counts


def exclusions():
    words, prefixes = set(), []
    for line in (HERE / "wykluczone.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        for item in line.split():
            if item.endswith("*"):
                prefixes.append(item[:-1])
            else:
                words.add(item)
    return words, tuple(prefixes)


def sjp_lemmas():
    """Base forms of the pinned SJP.PL release that can enter the list."""
    with zipfile.ZipFile(fetch_pinned(SOURCES["odmiany"], "odmiany")) as z:
        odm = z.read("odm.txt").decode("utf-8")
    lemmas = {line.split(",", 1)[0].strip() for line in odm.splitlines()}
    return "".join(w + "\n" for w in sorted(w for w in lemmas if WORD.match(w)))


def candidates():
    pl = frequencies(fetch("czestosc_pl"))
    english = set(list(frequencies(fetch("czestosc_en")))[:ENGLISH_TOP])
    excluded, prefixes = exclusions()
    # Częstość samej formy podstawowej: suma form liczyłaby też inne słowa o tej samej pisowni
    # (forma „tylka” jest rzadka, ale wśród form bywa „tylko”).
    lemmas = LEMMAS.read_text(encoding="utf-8").split()
    ranked = sorted(((pl.get(w, 0), w) for w in lemmas
                     if WORD.match(w) and w not in english and w not in excluded and not w.startswith(prefixes)
                     and pl.get(w, 0) >= MIN_COUNT), key=lambda x: (-x[0], x[1]))
    return [w for _, w in ranked]


def build():
    ranked = candidates()
    if len(ranked) < SIZE:
        sys.exit(f"za mało słów: {len(ranked)} < {SIZE}")
    return "".join(w + "\n" for w in sorted(ranked[:SIZE]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--candidates", type=int)
    parser.add_argument("--sjp", action="store_true", help="odbuduj sjp-lematy.txt z przypiętego wydania SJP.PL")
    args = parser.parse_args()
    if args.sjp:
        LEMMAS.write_text(sjp_lemmas(), encoding="utf-8")
        print(f"{LEMMAS}: {len(LEMMAS.read_text(encoding='utf-8').split())} form podstawowych")
        return
    if args.candidates is not None:
        print(" ".join(candidates()[:args.candidates]))
        return
    text = build()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT} nie zgadza się z budową; uruchom bez --check")
        print(f"{OUT.name}: zgodna, {SIZE} słów")
        return
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT}: {SIZE} słów")


if __name__ == "__main__":
    main()
