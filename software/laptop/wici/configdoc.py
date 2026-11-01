# SPDX-License-Identifier: MIT
"""The `configure` document (docs/spec/usb-protocol.md, "Dokument configure"): normalising and checking.

The station checks the document again and has the last word; this check gives the person preparing
the station a precise message per field before anything is sent. Limits follow firmware/src/config.h,
text rules follow SA1 (software/reference/reference.py, `_text`).
"""

import hashlib
import json
import re
import secrets
import unicodedata

DOC_MAX = 7680
SA1_MAX = 256          # treść SA1 po kodowaniu (docs/spec/oprogramowanie.md); stacja liczy najgorsze zgłoszenie
ADDRESSES, ADDRESS_MAX = 8, 64
PHRASES, PHRASE_MAX = 11, 96
STATIONS_MAX = 1000
PRIORITY_KEYS_MAX = 50
PROFILES = ("lora-sf7", "p1")
REJECTED_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
UNICODE_VERSION = "16.0.0"   # tabele Unicode oprogramowania stacji (firmware/src/unicode_tables.h)
HEX = re.compile(r"[0-9a-f]*")
SPACES = re.compile(r"\s+")


def unicode_warning():
    """None, or why this Python may judge texts differently than the station (another Unicode version)."""
    if unicodedata.unidata_version == UNICODE_VERSION:
        return None
    return (f"Unicode {unicodedata.unidata_version} w Pythonie, {UNICODE_VERSION} w stacji: "
            "stacja może odrzucić tekst, który laptop przepuścił (albo odwrotnie)")


def destination(key, name):
    """Reticulum destination hash: sha256(sha256(name)[:10] + sha256(key)[:16])[:16]."""
    return hashlib.sha256(hashlib.sha256(name.encode()).digest()[:10] + hashlib.sha256(key).digest()[:16]).digest()[:16]


def clean_text(value):
    """What the form does with typed or pasted text: invisible format characters (Cf: soft hyphen, ZWSP, BOM)
    dropped, NFC, whitespace runs (also line breaks and tabs) to one space, edges trimmed, quotes to „ ”
    and backslash to /."""
    text = "".join(c for c in str(value) if unicodedata.category(c) != "Cf")
    text = SPACES.sub(" ", unicodedata.normalize("NFC", text)).strip().replace("\\", "/")
    out, opening = [], True
    for c in text:
        if c == '"':
            c = "„" if opening else "”"
            opening = not opening
        out.append(c)
    return "".join(out)


def text_problem(value, maximum, minimum=0):
    """None, or the reason why the text cannot go into SA1."""
    size = len(value.encode("utf-8"))
    if size < minimum:
        return "pole jest puste"
    if size > maximum:
        return f"za długie: {size} B, najwyżej {maximum} B"
    bad = [c for c in value if c in '"\\' or unicodedata.category(c) in REJECTED_CATEGORIES]
    if bad:
        return "niedozwolony znak U+%04X" % ord(bad[0])
    if unicodedata.normalize("NFC", value) != value:
        return "tekst nie jest w postaci NFC"
    return None


def normalize(doc):
    """Clean texts and hex, drop fields the role does not use; unknown values pass to `check`."""
    if not isinstance(doc, dict):
        return doc
    out = dict(doc)
    for key in ("ifac",):
        if isinstance(out.get(key), str):
            out[key] = out[key].strip().lower()
    if isinstance(out.get("addresses"), list):
        out["addresses"] = [clean_text(a) if isinstance(a, str) else a for a in out["addresses"]]
    if isinstance(out.get("phrases"), list):
        out["phrases"] = [[clean_text(t) if isinstance(t, str) else t for t in p] if isinstance(p, list) else p
                          for p in out["phrases"]]
    receiver = out.get("receiver")
    if isinstance(receiver, dict):
        out["receiver"] = {k: ({f: v.strip().lower() if isinstance(v, str) else v for f, v in c.items()}
                               if isinstance(c, dict) else c) for k, c in receiver.items()}
    if isinstance(out.get("priority_keys"), list):
        out["priority_keys"] = [{**entry, **{field: entry[field].strip().lower()
                                                 for field in ("ed25519", "x25519")
                                                 if isinstance(entry.get(field), str)}}
                                if isinstance(entry, dict) else entry
                                for entry in out["priority_keys"]]
    if out.get("role") == "wezel":
        out = {k: out[k] for k in ("role", "ifac", "radio", "network", "priority_keys") if k in out}
    return out


def _hex(value, length):
    return isinstance(value, str) and len(value) == length and HEX.fullmatch(value) is not None


def _number(value, zero=False):
    return type(value) is int and (0 if zero else 1) <= value <= 0xFFFE


def check(doc):
    """List of (field, message) problems; empty when the station should accept the document."""
    if not isinstance(doc, dict):
        return [("", "dokument nie jest obiektem JSON")]
    problems = []
    role = doc.get("role")
    allowed = {"role", "ifac", "radio", "network", "priority_keys"} | ({"addresses", "receiver", "stations", "phrases"} if role == "stacja" else set())
    for key in sorted(set(doc) - allowed):
        problems.append((key, "pole nieznane albo niepotrzebne dla tej roli"))
    if role not in ("stacja", "wezel"):
        problems.append(("role", "wybierz stację schronienia albo węzeł stanowiska"))
    if not _hex(doc.get("ifac"), 32):
        problems.append(("ifac", "kod dostępu sieci to 32 cyfry szesnastkowe"))
    radio = doc.get("radio")
    if not (isinstance(radio, dict) and set(radio) == {"profile"} and radio["profile"] in PROFILES):
        problems.append(("radio", "wybierz profil radiowy"))
    network = doc.get("network")
    if network is not None:
        required = {"id", "station", "root", "parent", "backup_parent", "receiver_main", "receiver_backup"}
        if not isinstance(network, dict) or set(network) != required or any(
                not _number(network.get(field), field in ("parent", "backup_parent")) for field in required):
            problems.append(("network", "niepoprawne numery sieci, stacji, odbiorców lub tras"))
        else:
            n = network
            distinct = len({n["station"], n["root"], n["receiver_main"], n["receiver_backup"]}) == 4 if role == "stacja" else len({n["root"], n["receiver_main"], n["receiver_backup"]}) == 3
            route_ok = ((n["station"] == n["root"] and n["parent"] == n["backup_parent"] == 0)
                        if role == "wezel" else
                        (n["station"] != n["root"] and n["parent"] not in (0, n["station"], n["receiver_main"], n["receiver_backup"])
                         and n["backup_parent"] not in (n["station"], n["receiver_main"], n["receiver_backup"])
                         and (n["backup_parent"] == 0 or n["backup_parent"] != n["parent"])))
            if not distinct or not route_ok:
                problems.append(("network", "numery muszą być rozłączne, a trasa prowadzić do innego węzła"))
    priority_keys = doc.get("priority_keys", [])
    if "network" in doc and not priority_keys:
        problems.append(("priority_keys", "numbered stations need neighbor authentication keys"))
    elif priority_keys or "priority_keys" in doc:
        seen = set()
        if network is None or not isinstance(priority_keys, list) or len(priority_keys) > PRIORITY_KEYS_MAX:
            problems.append(("priority_keys", "niepoprawna lista kluczy pochodzenia K1"))
        else:
            for i, entry in enumerate(priority_keys):
                number = entry.get("id") if isinstance(entry, dict) else None
                if (not isinstance(entry, dict) or set(entry) != {"id", "ed25519", "x25519"} or
                        not _number(number) or not _hex(entry.get("ed25519"), 64) or
                        not _hex(entry.get("x25519"), 64) or number in seen or
                        isinstance(network, dict) and number in
                        (network.get("station"), network.get("receiver_main"), network.get("receiver_backup"))):
                    problems.append((f"priority_keys.{i}", "invalid or repeated station number or public key"))
                else:
                    seen.add(number)
    if role != "stacja":
        return problems
    addresses = doc.get("addresses")
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= ADDRESSES:
        problems.append(("addresses", f"od 1 do {ADDRESSES} adresów"))
    else:
        for i, a in enumerate(addresses):
            p = text_problem(a, ADDRESS_MAX, 1) if isinstance(a, str) else "to nie jest tekst"
            if p:
                problems.append((f"addresses.{i}", p))
    stations = doc.get("stations")
    if type(stations) is not int or not 1 <= stations <= STATIONS_MAX:
        problems.append(("stations", f"liczba od 1 do {STATIONS_MAX}"))
    phrases = doc.get("phrases")
    if not isinstance(phrases, list) or len(phrases) > PHRASES:
        problems.append(("phrases", f"lista fraz (może być pusta), najwyżej {PHRASES}"))
    else:
        for i, p in enumerate(phrases):
            if not isinstance(p, list) or len(p) != 3:
                problems.append((f"phrases.{i}", "fraza ma trzy wersje: PL, UK, EN"))
                continue
            for lang, t in enumerate(p):
                q = text_problem(t, PHRASE_MAX, 1 if lang == 0 else 0) if isinstance(t, str) else "to nie jest tekst"
                if q:
                    problems.append((f"phrases.{i}.{lang}", q))
    receiver = doc.get("receiver")
    if not (isinstance(receiver, dict) and set(receiver) == {"main", "backup"}):
        problems.append(("receiver", "karta odbiorcy ma tożsamość główną i zapasową"))
    else:
        for which in ("main", "backup"):
            card = receiver[which]
            expected = {"lxmf", "key", "id", "net_id", "x25519"} if network is not None else {"lxmf", "key"}
            if not (isinstance(card, dict) and set(card) == expected):
                problems.append((f"receiver.{which}", "niepoprawne pola tożsamości odbiorcy"))
            elif not _hex(card["key"], 128):
                problems.append((f"receiver.{which}.key", "klucz publiczny to 128 cyfr szesnastkowych"))
            elif not _hex(card["lxmf"], 32):
                problems.append((f"receiver.{which}.lxmf", "adres LXMF to 32 cyfry szesnastkowe"))
            elif destination(bytes.fromhex(card["key"]), "lxmf.delivery").hex() != card["lxmf"]:
                problems.append((f"receiver.{which}.lxmf", "adres LXMF nie należy do tego klucza (błąd przepisania?)"))
            elif network is not None and (not _hex(card["x25519"], 64) or card["x25519"] != card["key"][:64]):
                problems.append((f"receiver.{which}.x25519", "klucz koperty nie należy do tożsamości odbiorcy"))
            elif network is not None and (not _number(card["id"]) or not _number(card["net_id"]) or
                                          not isinstance(network, dict) or
                                          card["net_id"] != network.get("id") or
                                          card["id"] != network.get("receiver_" + which)):
                problems.append((f"receiver.{which}.id", "numer i sieć muszą zgadzać się z planem"))
        if not any(f.startswith("receiver") for f, _ in problems) and receiver["main"]["lxmf"] == receiver["backup"]["lxmf"]:
            problems.append(("receiver.backup", "tożsamość zapasowa musi być inna niż główna"))
    return problems


def compact(value, limit):
    """Compact UTF-8 JSON without escape sequences (texts were checked), at most `limit` bytes.

    Shared by the `configure` document and protocol lines (usbproto.encode adds the LF)."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if "\\" in text:
        raise ValueError("wymagałoby sekwencji ucieczki")
    data = text.encode("utf-8")
    if len(data) > limit:
        raise ValueError(f"za długie: {len(data)} B, najwyżej {limit} B")
    return data


def encode(doc):
    """Bytes sent in the `configure` transfer: coded like protocol lines (UTF-8, no escape sequences)."""
    return compact(doc, DOC_MAX)


def prepare(doc):
    """Normalise, check and encode: (doc, problems, data); `data` is None when there are problems."""
    doc = normalize(doc)
    problems = check(doc)
    if problems:
        return doc, problems, None
    try:
        return doc, [], encode(doc)
    except ValueError as e:
        return doc, [("", str(e))], None


def new_ifac():
    """A fresh network access code: only for the first station of a new network."""
    return secrets.token_hex(16)
