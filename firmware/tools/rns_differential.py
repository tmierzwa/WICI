# SPDX-License-Identifier: MIT
"""Differential trial of the station Reticulum core against reference Reticulum (Python).

The same inbound traffic goes to the core (tests/native/rnscore_check, commands t_*) and to Reticulum
in this process acting as the same station: the same identity as transport identity (transport
enabled, as in the port), a "wici.sa1" destination proving every packet, one interface that records
what Reticulum transmits. Between two waits both sides must transmit the same packets (as a
multiset), and after every step keep the same paths (hops and next hop) to every destination of the trial
(firmware/reticulum-core.md, acceptance criterion 2). Path responses for the station destination
carry a new random hash and signature on each side, so for them only the fields before the random
hash are compared, and only whether they were sent (the core sends at most one a second).

Traffic: announces (direct, through a transport node, path responses, rebroadcasts of neighbours), path requests (station
destination, known destination, unknown destination asked twice), packets in transport for known and
unknown destinations, proofs of forwarded packets, packets for the station, and mutated copies of all
of them (byte flips without the IFAC bit, truncation, changed hops), all built with the core check
program. Time: Reticulum runs in real time, the core on the virtual clock of the check program; the
trial waits long enough for the retransmissions of both (path response grace, rebroadcasts).

Run with a Python that has Reticulum at the pinned commit (e40191b):
  .venv-rns/bin/python firmware/tools/rns_differential.py --check /path/to/rnscore_check --seed 1
(tests/test_rns_differential.py builds the check program and runs this).

Prints one JSON object in the last line (steps, differences); exit code 0 when there is no difference.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME, ASPECT = "wici", "sa1"
NAME = f"{APP_NAME}.{ASPECT}"
STATION_SEED = b"wici differential station"
PATH_REQUEST = hashlib.sha256(hashlib.sha256(b"rnstransport.path.request").digest()[:10]).digest()[:16]
CONTEXT_PATH_RESPONSE = 0x0B
# Okna czasu: odpowiedź na zapytanie o trasę po 0,4 s i pierwsza retransmisja ogłoszenia do 0,5 s
# (Python przegląda tablicę ogłoszeń co sekundę z wątku co 0,25 s: do 1,75 s, zapas na wolny komputer),
# druga retransmisja 5,5 s po pierwszej (Python do 1,25 s później). Pakiety porównywane w odcinkach między oczekiwaniami.
WINDOWS_MS = (2500, 7200)


def key(label: str) -> bytes:
    return hashlib.sha512(label.encode()).digest()


class Core:
    """Commands for the core check program; the transport run is replayed from the start each time."""

    def __init__(self, binary: str):
        self.binary = binary

    def ask(self, commands):
        stdin = "".join(f"{command} {data.hex()}\n" for command, data in commands)
        run = subprocess.run([self.binary], input=stdin, capture_output=True, text=True, timeout=600,
                             env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1"))
        if run.returncode != 0 or run.stderr:
            raise RuntimeError(f"rnscore_check failed: {run.stderr[-2000:]}")
        lines = run.stdout.splitlines()
        if len(lines) != len(commands):
            raise RuntimeError(f"rnscore_check: {len(lines)} lines for {len(commands)} commands")
        return lines

    def one(self, command, data):
        return self.ask([(command, data)])[0]


class Builder:
    """Packets of the trial, built by the core check program (checked against Reticulum vectors)."""

    def __init__(self, core: Core):
        self.core = core

    def public_key(self, private_key: bytes) -> bytes:
        return bytes.fromhex(self.core.one("public_key", private_key))

    def identity(self, private_key: bytes) -> bytes:
        return bytes.fromhex(self.core.one("identity_hash", self.public_key(private_key)))

    def address(self, private_key: bytes) -> bytes:
        return bytes.fromhex(self.core.one("destination_hash", self.identity(private_key) + NAME.encode()))

    def packet(self, flags: int, destination: bytes, data: bytes, context: int = 0, transport_id: bytes = bytes(16),
               hops: int = 0) -> bytes:
        header = bytes([(flags >> 6) & 1, (flags >> 5) & 1, (flags >> 4) & 1, (flags >> 2) & 3, flags & 3, hops])
        return bytes.fromhex(self.core.one("pack", header + transport_id + destination + bytes([context]) + data))

    def announce(self, private_key: bytes, emitted: int, app_data: bytes = b"") -> bytes:
        random_hash = hashlib.sha256(private_key + emitted.to_bytes(8, "big")).digest()[:5] + emitted.to_bytes(5, "big")
        return bytes.fromhex(self.core.one("build_announce", private_key + random_hash + b"\x00" + app_data))

    @staticmethod
    def via(raw: bytes, transport_id: bytes, hops: int) -> bytes:
        return bytes([raw[0] | 0x50, hops]) + transport_id + raw[2:]

    @staticmethod
    def response(raw: bytes) -> bytes:
        at = 34 if raw[0] & 0x40 else 18
        return raw[:at] + bytes([CONTEXT_PATH_RESPONSE]) + raw[at + 1:]

    def path_request(self, destination: bytes, tag: bytes, requestor: bytes = b"", hops: int = 0) -> bytes:
        return self.packet(0x08, PATH_REQUEST, destination + requestor + tag, hops=hops)

    def packet_hash(self, raw: bytes) -> bytes:
        return bytes.fromhex(self.core.one("unpack", raw).split()[-1])

    def encrypted(self, public_key: bytes, payload: bytes, n: int) -> bytes:
        ephemeral = hashlib.sha256(b"eph" + bytes([n])).digest()
        iv = hashlib.sha256(b"iv" + bytes([n])).digest()[:16]
        return bytes.fromhex(self.core.one("encrypt", public_key + ephemeral + iv + payload))


def scenario(builder: Builder, station_key: bytes, rng: random.Random, mutations: int):
    """Steps ("in", raw) and ("wait", ms); destinations whose paths are compared."""
    station_identity = builder.identity(station_key)
    station_address = builder.address(station_key)
    keys = {name: key(f"wici differential {name}") for name in ("near", "far", "late", "other")}
    dests = {name: builder.address(k) for name, k in keys.items()}
    relay, relay2 = hashlib.sha256(b"relay").digest()[:16], hashlib.sha256(b"relay2").digest()[:16]
    near = builder.announce(keys["near"], 1_790_000_000)
    far = builder.via(builder.announce(keys["far"], 1_790_000_001), relay, 1)
    late = builder.announce(keys["late"], 1_790_000_002)
    other = builder.via(builder.announce(keys["other"], 1_790_000_003, b"WICI"), relay2, 3)
    newer_near = builder.via(builder.announce(keys["near"], 1_790_000_100), relay, 2)
    to_far = builder.packet(0x50, dests["far"], b"far" * 20, transport_id=station_identity, hops=2)
    to_near = builder.packet(0x70, dests["near"], b"near" * 20, transport_id=station_identity)
    to_unknown = builder.packet(0x50, bytes(16), b"unknown" * 8, transport_id=station_identity)
    proof_far = builder.packet(0x03, builder.packet_hash(to_far)[:16], bytes(64), hops=1)
    station_public = builder.public_key(station_key)
    to_station = builder.packet(0x00, station_address, builder.encrypted(station_public, b"SA1 trial", 1))
    tag = lambda n: hashlib.sha256(b"tag" + bytes([n])).digest()[:16]  # noqa: E731

    steps = [("in", near), ("in", far), ("in", other), ("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1]),
             ("in", builder.path_request(station_address, tag(1))), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["far"], tag(2), requestor=relay2)),
             ("in", builder.path_request(dests["far"], tag(2), requestor=relay2)), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["near"], tag(3), requestor=dests["near"])), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["late"], tag(4))), ("in", builder.path_request(dests["late"], tag(5))),
             ("in", late), ("wait", WINDOWS_MS[0]),
             # Powtórki sąsiadów po pierwszej retransmisji: dwie lokalne kończą wpis bez drugiego nadania.
             ("in", builder.via(late, relay, 1)), ("in", builder.via(late, relay2, 1)), ("wait", WINDOWS_MS[1]),
             ("in", builder.announce(keys["late"], 1_790_000_050)), ("wait", WINDOWS_MS[0]),
             ("in", builder.via(builder.announce(keys["late"], 1_790_000_050), relay, 2)), ("wait", WINDOWS_MS[1]),
             ("in", to_far), ("in", to_far), ("in", to_near), ("in", to_unknown), ("in", proof_far), ("in", proof_far),
             ("in", to_station), ("in", to_station),
             ("in", newer_near), ("in", builder.via(newer_near[:1] + newer_near[1:2] + newer_near[2:], relay2, 2)),
             ("in", builder.response(builder.via(builder.announce(keys["other"], 1_790_000_200), relay, 1))),
             ("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1])]
    corpus = [near, far, late, other, newer_near, to_far, to_near, to_unknown, proof_far, to_station,
              builder.path_request(dests["far"], tag(9)), builder.path_request(station_address, tag(10))]
    for n in range(mutations):
        raw = bytearray(rng.choice(corpus))
        kind = rng.randrange(4)
        if kind == 0:
            at = rng.randrange(len(raw))
            raw[at] ^= 1 << rng.randrange(7 if at == 0 else 8)   # bez bitu IFAC: sprawdza go interfejs
        elif kind == 1:
            raw = raw[:rng.randrange(1, len(raw))]
        elif kind == 2:
            raw[1] = rng.randrange(256)
        else:
            raw[rng.randrange(2, len(raw))] = rng.randrange(256)
        steps.append(("in", bytes(raw)))
        if n % 16 == 15 or n == mutations - 1:
            steps += [("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1])]
    return steps, list(dests.values()) + [station_address], station_address


class Capture:
    """Reticulum interface that records what Transport transmits (no radio)."""

    def __init__(self, RNS):
        base = RNS.Interfaces.Interface.Interface

        class Interface(base):
            def __init__(self):
                super().__init__()
                self.name = "P1"
                self.IN = self.OUT = True
                self.online = True
                self.bitrate = 10**9          # bez limitu ogłoszeń interfejsu: ten limit ma kolejka P1
                self.HW_MTU = 500
                self.ingress_control = False  # tabela różnic: rdzeń nie ma kontroli ruchu przychodzącego
                self.sent = []
                self.lock = threading.Lock()

            def process_outgoing(self, data):
                with self.lock:
                    self.sent.append(bytes(data))
                self.txb += len(data)

            def __str__(self):
                return "Capture[P1]"

        self.interface = Interface()

    def take(self):
        with self.interface.lock:
            sent, self.interface.sent = self.interface.sent, []
        return sent


def start_python(station_key: bytes):
    import RNS  # noqa: E402 (needs the reference Reticulum)

    work = tempfile.mkdtemp(prefix="wici_rns_diff_")
    config = """
[reticulum]
  enable_transport = Yes
  share_instance = No
  panic_on_interface_error = Yes

[logging]
  loglevel = 0

[interfaces]
"""
    os.makedirs(os.path.join(work, "storage"))
    with open(os.path.join(work, "config"), "w") as f:
        f.write(config)
    identity = RNS.Identity.from_bytes(station_key)
    identity.to_file(os.path.join(work, "storage", "transport_identity"))
    reticulum = RNS.Reticulum(work)
    capture = Capture(RNS)
    # Jak interfejs z konfiguracji (tryb pełny, bez IFAC: kod dostępu zdejmuje interfejs P1 przed stosem).
    reticulum._add_interface(capture.interface)
    destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    destination.set_proof_strategy(RNS.Destination.PROVE_ALL)
    busy = [0]
    inbound = RNS.Transport._inbound

    def counted(packet):
        busy[0] += 1
        try:
            inbound(packet)
        finally:
            busy[0] -= 1

    RNS.Transport._inbound = counted

    def settle():
        quiet = 0
        while quiet < 3:
            time.sleep(0.005)
            quiet = quiet + 1 if RNS.Transport.inbound_queues.qsize() == 0 and busy[0] == 0 else 0

    return RNS, capture, destination, settle


def python_paths(RNS, dests):
    out = {}
    for dest in dests:
        entry = RNS.Transport.path_table.get(dest)
        out[dest.hex()] = None if entry is None else [entry[2], entry[1].hex()]
    return out


def core_paths(lines, dests):
    out = {}
    for dest, line in zip(dests, lines):
        fields = line.split()
        out[dest.hex()] = None if line == "none" or fields[2] == "0" else [int(fields[0]), fields[3]]
    return out


def normalized(raws, station_address):
    """Multiset of packets; announces of the station destination without random hash and signature,
    and only once each: the core answers path requests for it at most once a second
    (reticulum-core.md, difference table), Reticulum to every request."""
    out, own = [], set()
    for raw in raws:
        flags = raw[0]
        at = 34 if flags & 0x40 else 18
        if flags & 0x03 == 0x01 and raw[at - 16:at] == station_address:
            own.add(raw[:at + 1 + 64 + 10].hex())   # nagłówek, kontekst, klucz publiczny, skrót nazwy
        else:
            out.append(raw.hex())
    return sorted(out) + sorted(own)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", required=True, help="tests/native/rnscore_check built by tests/test_rnscore.py")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mutations", type=int, default=64)
    args = parser.parse_args()

    core = Core(args.check)
    builder = Builder(core)
    station_key = key("wici differential station")
    steps, dests, station_address = scenario(builder, station_key, random.Random(args.seed), args.mutations)

    # Rdzeń: cała sekwencja naraz na zegarze wirtualnym; po każdym kroku pakiety i trasy.
    commands = [("t_begin", station_key)]
    now = 1000
    for kind, value in steps:
        if kind == "in":
            commands.append(("t_in", value))
        else:
            now += value
            commands.append(("t_clock", now.to_bytes(8, "big")))
        commands.append(("t_out", b""))
        commands += [("t_known", dest) for dest in dests]
    lines = core.ask(commands)[1:]
    per_step = 2 + len(dests)
    core_results = []
    for i in range(len(steps)):
        chunk = lines[i * per_step:(i + 1) * per_step]
        sent = [] if chunk[1] == "-" else [bytes.fromhex(x) for x in chunk[1].split()]
        core_results.append((sent, core_paths(chunk[2:], dests)))

    RNS, capture, destination, settle = start_python(station_key)
    if destination.hash != station_address:
        raise RuntimeError("station address differs between the core and Reticulum")
    capture.take()
    differences = []
    python_segment, core_segment = [], []
    for i, (kind, value) in enumerate(steps):
        if kind == "in":
            RNS.Transport.inbound(value, capture.interface)
            settle()
        else:
            time.sleep(value / 1000)
            settle()
        python_segment += capture.take()
        python_path = python_paths(RNS, dests)
        core_sent, core_path = core_results[i]
        core_segment += core_sent
        step = {"step": i, "kind": kind, "input": value.hex() if kind == "in" else value}
        if kind == "wait":
            if normalized(python_segment, station_address) != normalized(core_segment, station_address):
                differences.append({**step, "python_sent": [x.hex() for x in python_segment],
                                    "core_sent": [x.hex() for x in core_segment]})
            python_segment, core_segment = [], []
        if python_path != core_path:
            differences.append({**step, "python_paths": python_path, "core_paths": core_path})

    # Jeden wiersz na końcu (Reticulum pisze dziennik na standardowe wyjście).
    print(json.dumps({"reticulum": "e40191b", "seed": args.seed, "steps": len(steps), "differences": differences}))
    sys.stdout.flush()
    os._exit(0 if not differences else 1)


if __name__ == "__main__":
    main()
