# SPDX-License-Identifier: MIT
"""Test vectors for the station Reticulum core, made by reference Reticulum (Python) at the pinned commit.

Stage R0 of the core (firmware/reticulum-core.md): identity (keys, hash, signatures, including a
non-canonical signature with S + L), encryption to an identity (token, including damaged tokens and
tokens with a valid HMAC over a bad ciphertext, as any sender can make them, and tokens
whose ephemeral key is a low-order or non-canonical X25519 point) and
packets (HEADER_1 as packed by Reticulum, HEADER_2 as rewritten by its transport, packet hash); stage R1:
announces, encryption to a ratchet, packet proofs, HKDF and the interface access code (IFAC); Ed25519
edge cases (low-order and mixed-order keys and R, non-canonical encodings) with crafted inputs. Every
expected value is what the reference implementation computes or returns; nothing is computed here
by other code. Randomness (ephemeral X25519 key, token IV, announce random hash) is replaced by a
seeded generator only for the duration of each call, so the output is the same on every run.

Run with a Python that has Reticulum at the pinned commit (e40191b, version 1.5.5):
  .venv-rns/bin/python firmware/tools/rns_vectors.py > tests/vectors/reticulum.json
tests/test_rns_vectors.py compares the committed file with a fresh run when WICI_RNS_PYTHON is set.
"""

import hashlib
import json
import os
import sys
import tempfile
import types
from unittest import mock

import RNS
from RNS.Cryptography import PKCS7, X25519PrivateKey, X25519PublicKey
from RNS.Cryptography.AES import AES_256_CBC

RNS_VERSION = "1.5.5"
RNS_COMMIT = "e40191b3d193b46b7f2d8a44424a594cd758839b"
APP_NAME = "wici"
ASPECT = "sa1"
# Rząd grupy Ed25519 (RFC 8032): podpis z S + L jest niekanoniczny i ma zostać odrzucony.
ED25519_L = 2**252 + 27742317777372353535851937790883648493
# Ciało Curve25519 i punkty niskiego rzędu (lista z libsodium, RFC 7748 rozdz. 6.1): wspólny sekret zerowy.
X25519_P = 2**255 - 19
X25519_LOW_ORDER = {
    "zero": 0,
    "one": 1,
    "order_8_a": 325606250916557431795983626356110631294008115727848805560023387167927233504,
    "order_8_b": 39382357235489614581723060781553021112529911719440698176882885853963445705823,
    "p_minus_1": X25519_P - 1,
    "p": X25519_P,
    "p_plus_1": X25519_P + 1,
}
# Kodowania niekanoniczne punktu bazowego i innych: wartość ≥ p albo ustawiony najstarszy bit.
X25519_NON_CANONICAL = {"p_plus_9": X25519_P + 9, "high_bit": 9 + 2**255, "all_ones": 2**256 - 1}


def seeded(label: str, length: int) -> bytes:
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.sha256(f"wici-r0:{label}:{counter}".encode()).digest()
        counter += 1
    return out[:length]


class Deterministic:
    """Replaces the randomness Reticulum draws while one vector is made."""

    def __init__(self, label: str):
        self.label, self.draws = label, 0

    def urandom(self, n: int) -> bytes:
        self.draws += 1
        return seeded(f"{self.label}:urandom:{self.draws}", n)

    def x25519(self):
        self.draws += 1
        return X25519PrivateKey.from_private_bytes(seeded(f"{self.label}:x25519:{self.draws}", 32))

    def __enter__(self):
        self.patches = [mock.patch("os.urandom", self.urandom),
                        mock.patch.object(X25519PrivateKey, "generate", self.x25519)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


def identity(label: str) -> RNS.Identity:
    return RNS.Identity.from_bytes(seeded(f"identity:{label}", 64))


def identity_vectors():
    out = []
    for label in ("a", "b"):
        ident = identity(label)
        signatures = []
        for message in (b"", b"WICI", seeded(f"message:{label}", 500)):
            signature = ident.sign(message)
            s = int.from_bytes(signature[32:], "little") + ED25519_L
            non_canonical = signature[:32] + s.to_bytes(32, "little")
            tampered = bytes([message[0] ^ 1]) + message[1:] if message else b"\x00"
            signatures.append({
                "message": message.hex(),
                "signature": signature.hex(),
                "valid": ident.validate(signature, message),
                "tampered_message": tampered.hex(),
                "tampered_valid": ident.validate(signature, tampered),
                "non_canonical_signature": non_canonical.hex(),
                "non_canonical_valid": ident.validate(non_canonical, message),
            })
        destination = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
        out.append({
            "private_key": ident.get_private_key().hex(),
            "public_key": ident.get_public_key().hex(),
            "hash": ident.hash.hex(),
            "destination_wici_sa1": destination.hash.hex(),
            "signatures": signatures,
        })
    return out


# Arytmetyka Ed25519 z RFC 8032 (rozdz. 5.1, kod wzorcowy w Pythonie) tylko do spreparowania wejść
# przypadków brzegowych: kluczy i podpisów, jakie może wysłać każdy nadawca. Wynik weryfikacji daje
# Reticulum (Identity.validate), nie ten kod.
ED_P = 2**255 - 19
ED_D = -121665 * pow(121666, ED_P - 2, ED_P) % ED_P
ED_I = pow(2, (ED_P - 1) // 4, ED_P)


def ed_add(a, b):
    (x1, y1, z1, t1), (x2, y2, z2, t2) = a, b
    a_ = (y1 - x1) * (y2 - x2) % ED_P
    b_ = (y1 + x1) * (y2 + x2) % ED_P
    c = 2 * t1 * t2 * ED_D % ED_P
    d = 2 * z1 * z2 % ED_P
    e, f, g, h = b_ - a_, d - c, d + c, b_ + a_
    return (e * f % ED_P, g * h % ED_P, f * g % ED_P, e * h % ED_P)


def ed_mul(k: int, point):
    result = (0, 1, 1, 0)
    while k:
        if k & 1:
            result = ed_add(result, point)
        point = ed_add(point, point)
        k >>= 1
    return result


def ed_encode(point) -> bytes:
    x, y, z, _ = point
    zi = pow(z, ED_P - 2, ED_P)
    x, y = x * zi % ED_P, y * zi % ED_P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def ed_decode(data: bytes):
    y = int.from_bytes(data, "little")
    sign, y = y >> 255, y & (2**255 - 1)
    x2 = (y * y - 1) * pow(ED_D * y * y + 1, ED_P - 2, ED_P) % ED_P
    x = pow(x2, (ED_P + 3) // 8, ED_P)
    if (x * x - x2) % ED_P:
        x = x * ED_I % ED_P
    if x & 1 != sign:
        x = ED_P - x
    return (x, y % ED_P, 1, x * y % ED_P)


ED_BASE = ed_decode((4 * pow(5, ED_P - 2, ED_P) % ED_P).to_bytes(32, "little"))
# Punkt rzędu 8 (lista punktów niskiego rzędu Ed25519, np. libsodium): składowa skrętna kluczy i R.
ED_TORSION = ed_decode(bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"))


def ed25519_edge_vectors():
    """Klucze i podpisy, w których implementacje Ed25519 się różnią (klucz i R niskiego rzędu, kodowania
    niekanoniczne, składowa skrętna przy weryfikacji bez i z kofaktorem): wynik Identity.validate."""
    assert ed_encode(ed_mul(8, ED_TORSION)) == ed_encode((0, 1, 1, 0)) != ed_encode(ed_mul(4, ED_TORSION))
    message = b"WICI"
    x25519 = identity("a").get_public_key()[:32]
    a = int.from_bytes(seeded("edge:a", 64), "little") % ED25519_L
    r = int.from_bytes(seeded("edge:r", 64), "little") % ED25519_L
    point_a = ed_mul(a, ED_BASE)
    identity_point = (1).to_bytes(32, "little")

    def k(r_bytes: bytes, a_bytes: bytes) -> int:
        return int.from_bytes(hashlib.sha512(r_bytes + a_bytes + message).digest(), "little") % ED25519_L

    def signature(r_bytes: bytes, s: int) -> bytes:
        return r_bytes + s.to_bytes(32, "little")

    cases = {}
    # Klucz i R niskiego rzędu z S = 0: równanie spełnione dla każdej wiadomości.
    for name, key in (("small_order_key_identity", identity_point),
                      ("small_order_key_order_2", (ED_P - 1).to_bytes(32, "little")),
                      ("small_order_key_order_8", ed_encode(ED_TORSION)),
                      ("non_canonical_key_identity", (ED_P + 1).to_bytes(32, "little"))):
        cases[name] = (key, signature(identity_point, 0))
    # R w kodowaniu niekanonicznym (punkt neutralny jako p + 1): S = k·a, więc R' = [S]B - [k]A = 0.
    a_bytes = ed_encode(point_a)
    r_non_canonical = (ED_P + 1).to_bytes(32, "little")
    cases["non_canonical_r"] = (a_bytes, signature(r_non_canonical, k(r_non_canonical, a_bytes) * a % ED25519_L))
    cases["canonical_r_identity"] = (a_bytes, signature(identity_point, k(identity_point, a_bytes) * a % ED25519_L))
    # Punkt neutralny z bitem znaku (x = 0, więc kodowanie niekanoniczne) i punkt rzędu 2 jako -1 + p.
    r_sign = bytes(identity_point[:31]) + b"\x80"
    cases["non_canonical_r_sign_bit"] = (a_bytes, signature(r_sign, k(r_sign, a_bytes) * a % ED25519_L))
    cases["non_canonical_key_sign_bit"] = (r_sign, signature(identity_point, 0))
    # Klucz ze składową skrętną: podpis poprawny tylko przy weryfikacji z kofaktorem.
    mixed_a = ed_encode(ed_add(point_a, ED_TORSION))
    r_bytes = ed_encode(ed_mul(r, ED_BASE))
    cases["mixed_order_key"] = (mixed_a, signature(r_bytes, (r + k(r_bytes, mixed_a) * a) % ED25519_L))
    # R ze składową skrętną przy zwykłym kluczu: to samo.
    mixed_r = ed_encode(ed_add(ed_mul(r, ED_BASE), ED_TORSION))
    cases["mixed_order_r"] = (a_bytes, signature(mixed_r, (r + k(mixed_r, a_bytes) * a) % ED25519_L))
    # Kontrola: zwykły podpis tym samym kluczem przyjęty.
    cases["plain"] = (a_bytes, signature(r_bytes, (r + k(r_bytes, a_bytes) * a) % ED25519_L))
    out = []
    for name, (key, sig) in cases.items():
        public_key = x25519 + key
        try:
            ident = RNS.Identity(create_keys=False)
            ident.load_public_key(public_key)
            valid = bool(ident.validate(sig, message))
        except Exception:   # klucz odrzucony przy wczytaniu: dla stacji to samo co podpis odrzucony
            valid = False
        out.append({"name": name, "public_key": public_key.hex(), "signature": sig.hex(), "message": message.hex(),
                    "valid": valid})
    return out


def token_vectors():
    out = []
    ident = identity("a")
    receiver = RNS.Identity.from_bytes(ident.get_private_key())
    for length in (0, 1, 15, 16, 17, 300):
        plaintext = seeded(f"plaintext:{length}", length)
        with Deterministic(f"token:{length}"):
            token = ident.encrypt(plaintext)
        # Kolejność losowań w Identity.encrypt: klucz efemeryczny, potem IV w Token.encrypt.
        ephemeral = seeded(f"token:{length}:x25519:1", 32)
        iv = seeded(f"token:{length}:urandom:2", 16)
        if X25519PrivateKey.from_private_bytes(ephemeral).public_key().public_bytes() != token[:32] or iv != token[32:48]:
            sys.exit(f"token {length}: recorded ephemeral key or IV differs from the token")
        out.append({
            "identity_private_key": ident.get_private_key().hex(),
            "ephemeral_private_key": ephemeral.hex(),
            "iv": iv.hex(),
            "plaintext": plaintext.hex(),
            "token": token.hex(),
            "decrypted": receiver.decrypt(token).hex(),
        })
    return out


def crafted_token_vectors():
    """Damaged tokens and tokens with a valid HMAC; decrypted is what Identity.decrypt returns (None = rejected)."""
    ident = identity("a")
    with Deterministic("crafted"):
        valid = ident.encrypt(b"WICI")
    eph = X25519PrivateKey.from_private_bytes(seeded("crafted:ephemeral", 32))
    shared = eph.exchange(ident.pub)
    derived = RNS.Cryptography.hkdf(length=RNS.Identity.DERIVED_KEY_LENGTH, derive_from=shared,
                                    salt=ident.get_salt(), context=ident.get_context())
    iv = seeded("crafted:iv", 16)

    def signed(ciphertext: bytes) -> bytes:
        # Każdy nadawca może wysłać dowolny szyfrogram z poprawnym HMAC: klucz HMAC wylicza z własnego klucza
        # efemerycznego i klucza publicznego celu. HMAC chroni tylko przed zmianą w drodze.
        parts = iv + ciphertext
        return eph.public_key().public_bytes() + parts + RNS.Cryptography.HMAC.new(derived[:32], parts).digest()

    def block(last: int) -> bytes:
        # Jeden blok AES-256-CBC, którego tekst jawny kończy się bajtem dopełnienia last.
        return AES_256_CBC.encrypt(seeded(f"crafted:block:{last}", 15) + bytes([last]), derived[32:], iv)

    def with_ephemeral(public: int) -> bytes:
        # Token z podanym kluczem efemerycznym i HMAC z klucza, który wyliczy odbiorca. Gdy Python odrzuca
        # punkt (wspólny sekret zerowy), HMAC jest z sekretu zerowego: odbiorca bez tego sprawdzenia przyjąłby token.
        pub = public.to_bytes(32, "little")
        try:
            secret = ident.prv.exchange(X25519PublicKey.from_public_bytes(pub))
        except ValueError:
            secret = bytes(32)
        key = RNS.Cryptography.hkdf(length=RNS.Identity.DERIVED_KEY_LENGTH, derive_from=secret,
                                    salt=ident.get_salt(), context=ident.get_context())
        parts = iv + AES_256_CBC.encrypt(PKCS7.pad(b"WICI"), key[32:], iv)
        return pub + parts + RNS.Cryptography.HMAC.new(key[:32], parts).digest()

    cases = {
        "bad_hmac": valid[:-1] + bytes([valid[-1] ^ 1]),
        "bad_iv": valid[:40] + bytes([valid[40] ^ 1]) + valid[41:],
        "bad_ciphertext": valid[:48] + bytes([valid[48] ^ 1]) + valid[49:],
        "truncated_to_ephemeral_key": valid[:32],
        "truncated_to_iv": valid[:48],
        "only_ephemeral_key_and_hmac": valid[:32] + valid[-32:],
        "valid_hmac_empty_ciphertext": signed(b""),
        "valid_hmac_ciphertext_not_whole_blocks": signed(block(1) + b"\x00"),
        "valid_hmac_padding_above_block": signed(block(0x20)),
        # Python nie sprawdza bajtów dopełnienia ani zera: tekst jawny to blok bez last bajtów.
        "valid_hmac_padding_zero": signed(block(0)),
        "valid_hmac_padding_inconsistent": signed(block(2)),
        **{f"ephemeral_low_order_{name}": with_ephemeral(value) for name, value in X25519_LOW_ORDER.items()},
        **{f"ephemeral_non_canonical_{name}": with_ephemeral(value) for name, value in X25519_NON_CANONICAL.items()},
    }
    return [{"name": name, "identity_private_key": ident.get_private_key().hex(), "token": token.hex(),
             "decrypted": None if (p := ident.decrypt(token)) is None else p.hex()}
            for name, token in cases.items()]


def parsed(raw: bytes) -> dict:
    p = RNS.Packet(None, raw)
    if not p.unpack():
        return {"raw": raw.hex(), "valid": False}
    return {
        "raw": raw.hex(),
        "valid": True,
        "header_type": p.header_type,
        "context_flag": p.context_flag,
        "transport_type": p.transport_type,
        "destination_type": p.destination_type,
        "packet_type": p.packet_type,
        "hops": p.hops,
        "transport_id": p.transport_id.hex() if p.transport_id else None,
        "destination_hash": p.destination_hash.hex(),
        "context": p.context,
        "data": p.data.hex(),
        "hash": p.get_hash().hex(),
        "truncated_hash": p.getTruncatedHash().hex(),
    }


def header_two(raw: bytes, transport_id: bytes) -> bytes:
    # Jak Transport.outbound w Pythonie: HEADER_2, TRANSPORT, niższe bity flag bez zmian, identyfikator po skokach.
    flags = (RNS.Packet.HEADER_2 << 6) | (RNS.Transport.TRANSPORT << 4) | (raw[0] & 0b00001111)
    return bytes([flags, raw[1]]) + transport_id + raw[2:]


def packet_vectors():
    out = []
    ident = identity("b")
    single = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    plain = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.PLAIN, "rnstransport", "path", "request")
    transport_id = seeded("transport-id", 16)
    for name, destination, data, context in (
        ("single_data", single, seeded("data:single", 120), RNS.Packet.NONE),
        ("single_data_empty", single, b"", RNS.Packet.NONE),
        ("plain_path_request", plain, single.hash + transport_id + seeded("tag", 16), RNS.Packet.NONE),
    ):
        with Deterministic(f"packet:{name}"):
            packet = RNS.Packet(destination, data, context=context, create_receipt=False)
            packet.pack()
        h1 = parsed(packet.raw)
        h2 = parsed(header_two(packet.raw, transport_id))
        out.append({"name": name, "header_1": h1, "header_2": h2})
    # Pakiety spreparowane: granice długości, liczba skoków, bity flag; valid to wynik Packet.unpack.
    # Klucz header_1 jak przy pakietach odrzuconych wyżej: surowe bajty, typ nagłówka wynika z flag.
    base = bytes.fromhex(out[1]["header_1"]["raw"])   # single_data_empty: nagłówek 19 B i 64 B tokenu
    dst = single.hash
    for name, raw in (
        ("too_short", b"\x00"),
        ("header_2_too_short", bytes([0x50, 0]) + transport_id[:8]),
        ("header_1_without_context", bytes([0x00, 0]) + dst),
        ("header_1_without_data", bytes([0x00, 0]) + dst + b"\x00"),
        ("header_1_one_byte_of_data", bytes([0x00, 0]) + dst + b"\x00\x01"),
        ("header_2_without_data", bytes([0x50, 0]) + transport_id + dst + b"\x00"),
        ("header_2_one_byte_of_data", bytes([0x50, 0]) + transport_id + dst + b"\x00\x01"),
        ("hops_127", base[:1] + bytes([127]) + base[2:]),
        ("hops_128", base[:1] + bytes([128]) + base[2:]),
        ("hops_255", base[:1] + bytes([255]) + base[2:]),
        ("ifac_flag_set", bytes([base[0] | 0x80]) + base[1:]),
        ("context_flag_set", bytes([base[0] | 0x20]) + base[1:]),
        ("link_proof_types", bytes([0x0F]) + base[1:]),
        ("context_byte_ff", base[:18] + b"\xff" + base[19:]),
        ("above_mtu", base[:19] + seeded("above-mtu", 600)),
    ):
        out.append({"name": name, "header_1": parsed(raw)})
    return out


ANNOUNCE_TIME = 1_790_000_000   # czas ogłoszeń w wektorach (time.time w Destination.announce)


def announce_packet(dest, app_data, label: str, ratchets: bool = False) -> bytes:
    """Ogłoszenie z Destination.announce (bez wysyłania), złożone przez Packet.pack."""
    # Zapis ratchetu w magazynie instancji pominięty: nie zmienia bajtów ogłoszenia.
    with Deterministic(label), mock.patch("time.time", return_value=ANNOUNCE_TIME + 0.5), \
            mock.patch.object(RNS.Identity, "_remember_ratchet"):
        dest.ratchets = None
        if ratchets:
            dest.enable_ratchets(os.path.join(tempfile.mkdtemp(prefix="wici_vectors_"), "ratchets"))
        packet = dest.announce(app_data=app_data, send=False)
        packet.pack()
    return packet.raw


def validated(raw: bytes):
    """Wynik Identity.validate_announce dla pakietu z pustą tablicą znanych celów i bez czarnej listy:
    ogłoszenie poprawne, a nie decyzja transportu (Transport.inbound sprawdza dalej tablice i limity)."""
    RNS.Identity.known_destinations = {}
    packet = RNS.Packet(None, raw)
    if not packet.unpack():
        return False
    # Zapamiętanie ratchetu w magazynie instancji pominięte: nie zmienia wyniku.
    with mock.patch.object(RNS.Identity, "_remember_ratchet"):
        return bool(RNS.Identity.validate_announce(packet))


def announce_vectors():
    ident, other = identity("c"), identity("a")
    # Cel IN rejestruje się w transporcie działającej instancji; rejestracja nie zmienia bajtów ogłoszenia.
    with mock.patch.object(RNS.Transport, "register_destination"):
        dest = RNS.Destination(ident, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    out = []

    def add(name, raw, **extra):
        out.append({"name": name, "raw": raw.hex(), "valid": validated(raw), **extra})

    plain = announce_packet(dest, None, "announce:plain")
    with_data = announce_packet(dest, seeded("announce:app_data", 40), "announce:app_data")
    ratchet = announce_packet(dest, b"WICI", "announce:ratchet", ratchets=True)
    ratchet_empty = announce_packet(dest, None, "announce:ratchet_empty", ratchets=True)
    # Granice: 465 B danych przechodzi przez węzeł transportowy (HEADER_2 do MTU), 481 B to najwięcej,
    # co składa Packet.pack (HEADER_1 do MTU).
    forwardable = announce_packet(dest, seeded("announce:465", 465 - 148), "announce:465")
    largest = announce_packet(dest, seeded("announce:481", 481 - 148), "announce:481")
    for name, raw in (("plain", plain), ("app_data", with_data), ("ratchet", ratchet), ("ratchet_empty", ratchet_empty),
                      ("data_465", forwardable), ("data_481", largest)):
        data = raw[19:]
        has_ratchet = bool(raw[0] & 0x20)
        add(name, raw, private_key=ident.get_private_key().hex(), random_hash=data[74:84].hex(),
            ratchet=data[84:116].hex() if has_ratchet else None,
            app_data=data[84 + (32 if has_ratchet else 0) + 64:].hex())

    # Spreparowane: valid to wynik Identity.validate_announce.
    def resigned(destination_hash: bytes, signer, public_key: bytes) -> bytes:
        # Podpis poprawny dla danych z innym skrótem celu: zgodność podpisu, ale nie adresu.
        data = plain[19:]
        body = public_key + data[64:84]
        signature = signer.sign(destination_hash + body)
        return plain[:2] + destination_hash + plain[18:19] + body + signature

    sig = plain[19 + 84:19 + 148]
    s = int.from_bytes(sig[32:], "little") + ED25519_L
    data_len = len(plain) - 19
    cases = {
        "tampered_app_data": with_data[:-1] + bytes([with_data[-1] ^ 1]),
        "tampered_signature": plain[:-1] + bytes([plain[-1] ^ 1]),
        "tampered_random_hash": plain[:19 + 80] + bytes([plain[19 + 80] ^ 1]) + plain[19 + 81:],
        "non_canonical_signature": plain[:19 + 84] + sig[:32] + s.to_bytes(32, "little") + plain[19 + 148:],
        "context_flag_without_ratchet": bytes([plain[0] | 0x20]) + plain[1:],
        "ratchet_without_context_flag": bytes([ratchet[0] & ~0x20 & 0xFF]) + ratchet[1:],
        "truncated_by_one": plain[:-1],
        "ratchet_truncated_by_one": ratchet[:-1],
        "only_public_key": plain[:19 + 64],
        "other_identity_key": plain[:19] + other.get_public_key() + plain[19 + 64:],
        "destination_mismatch": resigned(seeded("announce:other-destination", 16), ident, ident.get_public_key()),
        "signed_by_other_identity": resigned(dest.hash, other, other.get_public_key()),
        "data_packet_type": bytes([plain[0] & 0xFC]) + plain[1:],
        # Po przepisaniu na HEADER_2 (Transport.inbound) dane i podpis bez zmian.
        "header_2": header_two(plain, seeded("announce:transport-id", 16)),
        # 482 B danych: więcej, niż złoży Packet.pack; Python sprawdza podpis i odrzuca.
        "data_482": largest + b"\x00",
    }
    assert data_len == 148
    for name, raw in cases.items():
        add(name, raw)
    return out


def ratchet_token_vectors():
    """Identity.encrypt do klucza ratchetu celu; odszyfrowanie Identity.decrypt z tym ratchetem."""
    out = []
    ident = identity("a")
    receiver = RNS.Identity.from_bytes(ident.get_private_key())
    ratchet_private = seeded("ratchet:private", 32)
    ratchet = X25519PrivateKey.from_private_bytes(ratchet_private).public_key().public_bytes()
    for length in (0, 4, 16, 100):
        plaintext = seeded(f"ratchet:plaintext:{length}", length)
        with Deterministic(f"ratchet:{length}"):
            token = ident.encrypt(plaintext, ratchet=ratchet)
        ephemeral = seeded(f"ratchet:{length}:x25519:1", 32)
        iv = seeded(f"ratchet:{length}:urandom:2", 16)
        if token[:32] != X25519PrivateKey.from_private_bytes(ephemeral).public_key().public_bytes() or token[32:48] != iv:
            sys.exit(f"ratchet token {length}: recorded ephemeral key or IV differs from the token")
        out.append({
            "identity_public_key": ident.get_public_key().hex(),
            "ratchet": ratchet.hex(),
            "ephemeral_private_key": ephemeral.hex(),
            "iv": iv.hex(),
            "plaintext": plaintext.hex(),
            "token": token.hex(),
            # Odbiorca z ratchetem odszyfrowuje, sam klucz tożsamości nie.
            "decrypted_with_ratchet": receiver.decrypt(token, ratchets=[ratchet_private]).hex(),
            "decrypted_without_ratchet": None if (d := receiver.decrypt(token)) is None else d.hex(),
        })
    # Ratchet niskiego rzędu albo w kodowaniu niekanonicznym (wynik Identity.encrypt: token albo błąd).
    rejected = []
    for name, value in (("zero", 0), ("one", 1), ("p_plus_1", X25519_P + 1), ("high_bit", 9 + 2**255)):
        r = value.to_bytes(32, "little")
        with Deterministic(f"ratchet:low:{name}"):
            try:
                token = ident.encrypt(b"WICI", ratchet=r).hex()
            except ValueError:
                token = None
        rejected.append({"name": name, "ratchet": r.hex(), "token": token,
                         "ephemeral_private_key": seeded(f"ratchet:low:{name}:x25519:1", 32).hex(),
                         "iv": seeded(f"ratchet:low:{name}:urandom:2", 16).hex()})
    out.append({"identity_public_key": ident.get_public_key().hex(), "unusual_ratchets": rejected})
    return out


def proof_vectors():
    """Dowody pakietu: Identity.prove (podpis skrótu pakietu; jawny ze skrótem przed podpisem) i wynik
    PacketReceipt.validate_proof dla potwierdzenia z tożsamością celu."""
    ident, other = identity("b"), identity("a")
    raw = bytes.fromhex(packet_vectors()[0]["header_1"]["raw"])
    packet = RNS.Packet(None, raw)
    packet.unpack()
    signature = ident.sign(packet.packet_hash)
    implicit, explicit = signature, packet.packet_hash + signature
    receipt = types.SimpleNamespace(hash=packet.packet_hash, destination=types.SimpleNamespace(identity=ident),
                                    callbacks=types.SimpleNamespace(delivery=None))

    def validated(proof: bytes) -> bool:
        return bool(RNS.PacketReceipt.validate_proof(receipt, proof))

    def proof_packet(data: bytes) -> bytes:
        # Identity.prove: pakiet PROOF do ProofDestination (skrót pakietu ucięty), bez szyfrowania.
        p = RNS.Packet(packet.generate_proof_destination(), data, RNS.Packet.PROOF)
        p.pack()
        return p.raw

    s = int.from_bytes(signature[32:], "little") + ED25519_L
    cases = {
        "implicit": implicit,
        "explicit": explicit,
        "implicit_tampered": implicit[:-1] + bytes([implicit[-1] ^ 1]),
        "explicit_wrong_hash": bytes([explicit[0] ^ 1]) + explicit[1:],
        "explicit_tampered": explicit[:-1] + bytes([explicit[-1] ^ 1]),
        "implicit_non_canonical": signature[:32] + s.to_bytes(32, "little"),
        "signed_by_other": other.sign(packet.packet_hash),
        "explicit_signature_of_other_hash": packet.packet_hash + ident.sign(seeded("proof:other-hash", 32)),
        "length_63": implicit[:63],
        "length_65": implicit + b"\x00",
        "length_95": explicit[:95],
        "length_97": explicit + b"\x00",
        "empty": b"",
    }
    return {
        "identity_private_key": ident.get_private_key().hex(),
        "packet": raw.hex(),
        "packet_hash": packet.packet_hash.hex(),
        "implicit_packet": proof_packet(implicit).hex(),
        "explicit_packet": proof_packet(explicit).hex(),
        "cases": [{"name": n, "proof": d.hex(), "valid": validated(d)} for n, d in cases.items()],
    }


def hkdf_vectors():
    """RNS.Cryptography.hkdf bez kontekstu (jak w IFAC i tokenie): długości wokół bloku 32 B, sól pusta
    (zastępowana 32 B zer), krótka i 64 B (klucz IFAC jako sól maski)."""
    ikm = seeded("hkdf:ikm", 32)
    salts = {"none": b"", "short": seeded("hkdf:salt", 16), "ifac_key": seeded("hkdf:ifac-key", 64)}
    out = []
    for name, salt in salts.items():
        for length in (1, 31, 32, 33, 64, 516):
            out.append({"salt": salt.hex(), "ikm": ikm.hex(), "length": length,
                        "okm": RNS.Cryptography.hkdf(length=length, derive_from=ikm, salt=salt or None, context=None).hex()})
    return out


def ifac_interface(passphrase: str):
    """Interfejs z kodem dostępu IFAC 16 B dla passphrase (RNS/Reticulum.py, bez networkname: ifac_origin,
    ifac_key, ifac_identity) do RNS.Transport.handle_outgoing_ifac i handle_ifac (także rns_osp_node.py)."""
    origin_hash = RNS.Identity.full_hash(RNS.Identity.full_hash(passphrase.encode("utf-8")))
    key = RNS.Cryptography.hkdf(length=64, derive_from=origin_hash, salt=RNS.Reticulum.IFAC_SALT, context=None)
    return types.SimpleNamespace(ifac_size=16, ifac_key=key, ifac_identity=RNS.Identity.from_bytes(key),
                                 ifac_violation=lambda reason: None)


def ifac_vectors():
    """Kod dostępu interfejsu (IFAC) dla passphrase sieci WICI (32 cyfry szesnastkowe klucza, ifac_size =
    128 b): klucz jak RNS/Reticulum.py przy konfiguracji interfejsu, kod i maska z Transport.handle_outgoing_ifac,
    sprawdzenie z Transport.handle_ifac, także dla datagramów zmienionych i z kodem innej sieci."""
    interface = ifac_interface

    passphrase = "5749434954335f696661635f74657374"
    iface, other = interface(passphrase), interface("00" * 16)
    packet = packet_vectors()[0]
    # Pakiety HEADER_1 i HEADER_2 z wektorów, najkrótszy (3 B) i o długości MTU (500 B).
    raws = [bytes.fromhex(packet["header_1"]["raw"]), bytes.fromhex(packet["header_2"]["raw"]),
            bytes([0x00, 0x00]) + seeded("ifac:short", 1), bytes([0x01, 0x05]) + seeded("ifac:mtu", 498)]
    applied = [{"raw": r.hex(), "wire": RNS.Transport.handle_outgoing_ifac(iface, r).hex()} for r in raws]

    def checked(wire: bytes):
        ok, raw = RNS.Transport.handle_ifac(wire, iface)
        return raw.hex() if ok else None

    wire = bytes.fromhex(applied[0]["wire"])
    crafted = {
        "valid": wire,
        "tag_flipped": wire[:2] + bytes([wire[2] ^ 1]) + wire[3:],
        "header_flipped": bytes([wire[0] ^ 0x01]) + wire[1:],
        "payload_flipped": wire[:-1] + bytes([wire[-1] ^ 1]),
        "other_network": RNS.Transport.handle_outgoing_ifac(other, bytes.fromhex(applied[0]["raw"])),
        "truncated": wire[:-1],
        "tag_only": wire[:2 + 16 + 1],
    }
    return {
        "passphrase": passphrase,
        "ifac_size": 16,
        "ifac_key": iface.ifac_key.hex(),
        "applied": applied,
        "checked": [{"name": n, "wire": w.hex(), "raw": checked(w)} for n, w in crafted.items()],
    }


def main():
    if RNS.__version__ != RNS_VERSION:
        sys.exit(f"Reticulum {RNS.__version__}, expected {RNS_VERSION} ({RNS_COMMIT})")
    vectors = {
        "source": {"reticulum": RNS_VERSION, "commit": RNS_COMMIT, "tool": "firmware/tools/rns_vectors.py"},
        "identity": identity_vectors(),
        "ed25519_edge": ed25519_edge_vectors(),
        "token": token_vectors(),
        "crafted_token": crafted_token_vectors(),
        "packet": packet_vectors(),
        "announce": announce_vectors(),
        "ratchet_token": ratchet_token_vectors(),
        "proof": proof_vectors(),
        "hkdf": hkdf_vectors(),
        "ifac": ifac_vectors(),
    }
    json.dump(vectors, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
