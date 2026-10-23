# SPDX-License-Identifier: MIT
"""Differential trial of the station Reticulum core against reference Reticulum (Python).

The same inbound traffic goes to the core (tests/native/rnscore_check, commands t_*) and to Reticulum
in this process acting as the same station: the same identity as transport identity (transport
enabled, as in the port), a "wici.sa1" destination proving every packet, an interface that records
what Reticulum transmits. Between two waits both sides must transmit the same packets (as a
multiset), and after every step keep the same paths (hops and next hop) to every destination of the trial
(firmware/reticulum-core.md, acceptance criterion 2). Path responses for the station destination
carry a new random hash and signature on each side, so for them only the fields before the random
hash are compared, and only whether they were sent (the core sends at most one a second).

Traffic: announces (direct, through a transport node, path responses, rebroadcasts of neighbours), path requests (station
destination, known destination, unknown destination asked twice), packets in transport for known and
unknown destinations, proofs of forwarded packets, packets for the station; fixed cases (hops 126-128,
other contexts of new announces, a path response for a destination with a pending rebroadcast, path
requests up to the capacity of the announce table); then fresh packets of each kind (new announces and
emission times, new contents and tags), half of them mutated (hops, context, flags without the IFAC
bit, transport id, truncation, a body byte; a mutation that reaches a difference listed in the table
of firmware/reticulum-core.md is adjusted or left out), all built with the core check program.
Time: Reticulum runs in real time, the core on the virtual clock of the check program with poll()
every LOOP_MS as in the station loop; the trial waits long enough for the retransmissions of both.

With --interfaces 2 (stage R4, the OSP node) both sides have a second interface (1, USB): the fixed
traffic puts the direct neighbour, some path requests, packets in transport and a packet for the station
on it, and the mutated traffic arrives on a random interface; packets are compared with the interface
they leave on, and paths with the interface of their announce.

Run with a Python that has Reticulum at the pinned commit (e40191b):
  .venv-rns/bin/python firmware/tools/rns_differential.py --check /path/to/rnscore_check --seed 1
(tests/test_rns_differential.py builds the check program and runs this).

Prints one JSON object in the last line (steps, differences); exit code 0 when there is no difference.

With --stress-dump FILE (a dump of tests/native/rns_stress --dump) the tool checks instead that the
unmutated traffic of the hostile trial generator is valid Reticulum: the IFAC of each datagram (Transport.handle_ifac
with the trial network key) gives the packet before IFAC, the packet unpacks, announces have a valid
signature and the destination of their identity, packets in transport decrypt with the key of their
generator node and packets for the station with the station key, proofs of station packets validate with a
generator key, and path requests and link requests have the shape Reticulum expects; other proofs, link
traffic and regression packets (kinds proof, defect) only IFAC and unpacking. A kind outside this list is a
problem. Packets with 128 hops or more (the generator makes them on purpose) must be rejected by
Packet.unpack (RNS/Packet.py:250 at e40191b), and datagrams over the MTU (a random IFAC from the generator)
must fail IFAC; both are counted. Mutated datagrams are skipped.
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
PATH_REQUEST = hashlib.sha256(hashlib.sha256(b"rnstransport.path.request").digest()[:10]).digest()[:16]
CONTEXT_PATH_RESPONSE = 0x0B
# Okna czasu: odpowiedź na zapytanie o trasę po 0,4 s i pierwsza retransmisja ogłoszenia do 0,5 s
# (Python przegląda tablicę ogłoszeń co sekundę z wątku co 0,25 s: do 1,75 s, zapas na wolny komputer
# w CI), druga retransmisja 5,5 s po pierwszej (Python do 1,25 s później). Pakiety porównywane w odcinkach
# między oczekiwaniami.
WINDOWS_MS = (4000, 7200)
# Rdzeń w oczekiwaniu: poll() co LOOP_MS jak pętla stacji (najwyżej jedna retransmisja na poll()).
LOOP_MS = 20


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


def scenario(builder: Builder, station_key: bytes, rng: random.Random, mutations: int, interfaces: int = 1):
    """Steps ("in", raw, interface) and ("wait", ms); destinations whose paths are compared."""
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

    # Drugi interfejs (USB): sąsiad bezpośredni, zapytania o cel stacji i o cel za P1, pakiet w transporcie
    # z USB do celu za P1 i pakiet do stacji. Przy jednym interfejsie wszystko na interfejsie 0.
    usb = 1 if interfaces > 1 else 0
    steps = [("in", near, usb), ("in", far), ("in", other), ("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1]),
             ("in", builder.path_request(station_address, tag(1)), usb), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["far"], tag(2), requestor=relay2), usb),
             ("in", builder.path_request(dests["far"], tag(2), requestor=relay2)), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["near"], tag(3), requestor=dests["near"])), ("wait", WINDOWS_MS[0]),
             ("in", builder.path_request(dests["late"], tag(4))), ("in", builder.path_request(dests["late"], tag(5))),
             ("in", late), ("wait", WINDOWS_MS[0]),
             # Powtórki sąsiadów po pierwszej retransmisji: dwie lokalne kończą wpis bez drugiego nadania.
             ("in", builder.via(late, relay, 1)), ("in", builder.via(late, relay2, 1)), ("wait", WINDOWS_MS[1]),
             ("in", builder.announce(keys["late"], 1_790_000_050)), ("wait", WINDOWS_MS[0]),
             ("in", builder.via(builder.announce(keys["late"], 1_790_000_050), relay, 2)), ("wait", WINDOWS_MS[1]),
             ("in", to_far, usb), ("in", to_far), ("in", to_near), ("in", to_unknown), ("in", proof_far), ("in", proof_far),
             ("in", to_station, usb), ("in", to_station),
             ("in", newer_near), ("in", builder.via(newer_near[:1] + newer_near[1:2] + newer_near[2:], relay2, 2)),
             ("in", builder.response(builder.via(builder.announce(keys["other"], 1_790_000_200), relay, 1))),
             ("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1])]
    windows = [("wait", WINDOWS_MS[0]), ("wait", WINDOWS_MS[1])]

    # Stałe przypadki: skoki na granicy PATHFINDER_M dla nowych ogłoszeń i pakietów w transporcie, inny
    # kontekst nowych ogłoszeń, odpowiedź na zapytanie (PATH_RESPONSE) o cel z czekającą retransmisją,
    # seria zapytań o znane cele do pojemności tablicy ogłoszeń (16).
    emitted = iter(range(1_790_000_300, 1_790_100_000))
    for hops in (126, 127, 128):
        k = key(f"wici differential hops {hops}")
        steps.append(("in", bytes([0x01, hops]) + builder.announce(k, next(emitted))[2:]))
        data = builder.packet(0x50, dests["far"], b"hops" * 10 + bytes([hops]), transport_id=station_identity)
        steps.append(("in", data[:1] + bytes([hops]) + data[2:]))   # pack odmawia skoków ≥ 128
    steps += windows
    for context in (0x01, 0x0B, 0xFE):
        raw = builder.announce(key(f"wici differential context {context}"), next(emitted))
        steps.append(("in", raw[:18] + bytes([context]) + raw[19:]))
    k = key("wici differential pending")
    steps.append(("in", builder.announce(k, next(emitted))))
    steps.append(("in", builder.response(builder.via(builder.announce(k, next(emitted)), relay, 1))))
    steps += windows
    series = [key(f"wici differential series {i}") for i in range(16)]
    steps += [("in", builder.response(builder.announce(k, next(emitted)))) for k in series] + windows
    steps += [("in", builder.path_request(builder.address(k), tag(100 + i))) for i, k in enumerate(series)] + windows

    # Mutacje świeżych pakietów (nowe ogłoszenia, czasy emisji, treści i znaczniki), żeby docierały do
    # decyzji transportu, a nie odpadały jako duplikaty; częściej pola nagłówka bez podpisu.
    known = list(keys.values()) + [key(f"wici differential fresh {i}") for i in range(4)]
    targets = list(dests.values()) + [station_address, bytes(16)]
    for n in range(mutations):
        kind = rng.randrange(5)
        if kind == 0:
            raw = builder.announce(rng.choice(known), next(emitted), rng.randbytes(rng.randrange(8)))
            if rng.randrange(2):
                raw = builder.via(raw, rng.choice((relay, relay2)), rng.randrange(1, 5))
            if rng.randrange(3) == 0:
                raw = builder.response(raw)
        elif kind == 1:
            raw = builder.packet(0x50, rng.choice(targets), rng.randbytes(1 + rng.randrange(200)), transport_id=station_identity,
                                 hops=rng.randrange(4))
        elif kind == 2:
            raw = builder.path_request(rng.choice(targets), rng.randbytes(16), requestor=rng.choice((b"", relay, relay2)))
        elif kind == 3:
            forwarded = builder.packet(0x50, rng.choice((dests["far"], dests["near"])), rng.randbytes(40),
                                       transport_id=station_identity, hops=1)
            steps.append(("in", forwarded))
            raw = builder.packet(0x03, builder.packet_hash(forwarded)[:16], rng.randbytes(64), hops=1)
        else:
            raw = builder.packet(0x00, station_address, builder.encrypted(station_public, rng.randbytes(20), n % 256))
        raw = bytearray(raw)
        if rng.randrange(2):
            header = 34 if raw[0] & 0x40 else 18
            m = rng.randrange(6)
            if m == 0:
                raw[1] = rng.randrange(256)
            elif m == 1:
                raw[header] = rng.randrange(256)                   # kontekst
            elif m == 2:
                raw[0] ^= 1 << rng.randrange(7)                    # bez bitu IFAC: sprawdza go interfejs
            elif m == 3 and header == 34:
                raw[2 + rng.randrange(16)] = rng.randrange(256)    # identyfikator transportu
            elif m == 4:
                raw = raw[:rng.randrange(1, len(raw))]
            else:
                raw[rng.randrange(2, len(raw))] = rng.randrange(256)
        if raw[0] & 0x03 == 0x02:
            raw[0] &= 0xFD   # LINKREQUEST: łącza są poza rdzeniem (zakres w reticulum-core.md)
        if raw[0] & 0x03 == 0x03:
            raw[0] &= 0xF3   # dowód z celem PLAIN albo GROUP: różnica w tabeli (reticulum-core.md)
        iface = rng.randrange(interfaces) if interfaces > 1 else 0
        # Do celu zapytań o trasę tylko zapytanie PLAIN DATA albo ogłoszenie; inny pakiet: różnica w tabeli
        # (reticulum-core.md).
        header = 34 if raw[0] & 0x40 else 18
        if bytes(raw[header - 16:header]) != PATH_REQUEST or raw[0] & 0x03 == 0x01 or raw[0] & 0x0F == 0x08:
            steps.append(("in", bytes(raw), iface))
        if n % 16 == 15 or n == mutations - 1:
            steps += windows
    steps = [s + (0,) if s[0] == "in" and len(s) == 2 else s for s in steps]
    return steps, list(dests.values()) + [station_address], station_address


class Capture:
    """Reticulum interfaces that record what Transport transmits (no radio): 0 P1, 1 USB."""

    def __init__(self, RNS, interfaces: int = 1):
        base = RNS.Interfaces.Interface.Interface

        class Interface(base):
            def __init__(self, name):
                super().__init__()
                self.name = name
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
                return f"Capture[{self.name}]"

        self.interfaces = [Interface(name) for name in ("P1", "USB")[:interfaces]]

    def take(self):
        """Packets transmitted since the last call as (interface, raw)."""
        out = []
        for n, interface in enumerate(self.interfaces):
            with interface.lock:
                sent, interface.sent = interface.sent, []
            out += [(n, raw) for raw in sent]
        return out


def start_python(station_key: bytes, interfaces: int = 1):
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
    capture = Capture(RNS, interfaces)
    # Jak interfejsy z konfiguracji (tryb pełny, bez IFAC: kod dostępu zdejmuje interfejs P1 przed stosem).
    for interface in capture.interfaces:
        reticulum._add_interface(interface)
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


def python_paths(RNS, dests, capture):
    """Hops, next hop and (with two interfaces) the interface of the announce (IDX_PT_RVCD_IF)."""
    out = {}
    for dest in dests:
        entry = RNS.Transport.path_table.get(dest)
        out[dest.hex()] = None if entry is None else [entry[2], entry[1].hex()]
        if entry is not None and len(capture.interfaces) > 1:
            out[dest.hex()].append(capture.interfaces.index(entry[5]))
    return out


def core_paths(lines, dests, routes=None):
    out = {}
    for i, (dest, line) in enumerate(zip(dests, lines)):
        fields = line.split()
        out[dest.hex()] = None if line == "none" or fields[2] == "0" else [int(fields[0]), fields[3]]
        if out[dest.hex()] is not None and routes is not None:
            out[dest.hex()].append(int(routes[i]))
    return out


def normalized(sent, station_address, station_identity):
    """Multiset of packets (with the interface they leave on); announces of the station destination without random hash and signature,
    and only once each: the core answers path requests for it at most once a second
    (reticulum-core.md, difference table), Reticulum to every request. Rebroadcasts of other announces
    (path responses too) without random hash and signature: the core sends the newest accepted announce
    of the destination, Reticulum the one that scheduled the rebroadcast (difference table)."""
    out, own = [], set()
    for interface, raw in sent:
        flags = raw[0]
        at = 34 if flags & 0x40 else 18
        head = f"{interface}:{raw[:at + 1 + 64 + 10].hex()}"   # nagłówek, kontekst, klucz publiczny, skrót nazwy
        if flags & 0x03 == 0x01 and raw[at - 16:at] == station_address:
            own.add(head)
        elif flags & 0x43 == 0x41 and raw[2:18] == station_identity:
            out.append(head)
        else:
            out.append(f"{interface}:{raw.hex()}")
    return sorted(out) + sorted(own)


def stress_dump(path: str):
    """Records of an rns_stress dump that Reticulum does not accept as the generator meant them."""
    import RNS  # noqa: E402 (needs the reference Reticulum)

    with open(path) as f:
        head = json.loads(f.readline())
        records = [json.loads(line) for line in f]

    class Interface:   # pola interfejsu, których używa Transport.handle_ifac
        ifac_size = head["ifac_size"]

        def ifac_violation(self, _):
            pass

    interface = Interface()
    origin = RNS.Identity.full_hash(RNS.Identity.full_hash(head["ifac_netkey"].encode("utf-8")))
    interface.ifac_key = RNS.Cryptography.hkdf(length=64, derive_from=origin, salt=RNS.Reticulum.IFAC_SALT, context=None)
    interface.ifac_identity = RNS.Identity.from_bytes(interface.ifac_key)
    app, aspect = head["app"].split(".")
    peers = [RNS.Identity.from_bytes(bytes.fromhex(k)) for k in head["peers"]]
    peer_destinations = {RNS.Destination.hash(peer, app, aspect): peer for peer in peers}
    station = RNS.Identity.from_bytes(bytes.fromhex(head["station_private_key"]))
    station_destination = RNS.Destination.hash(station, app, aspect)
    path_request = RNS.Destination.hash_from_name_and_identity("rnstransport.path.request", None)

    def problem(record, packet):
        kind = record["kind"]
        if kind in ("proof", "defect"):   # dowody i ruch łącza o losowej treści, próby regresji: IFAC i unpack
            return None
        if packet.packet_type == RNS.Packet.ANNOUNCE and kind == "announce":
            if not RNS.Identity.validate_announce(packet, only_validate_signature=True):
                return "announce signature"
            announced = RNS.Identity(create_keys=False)
            announced.load_public_key(packet.data[:RNS.Identity.KEYSIZE // 8])
            if RNS.Destination.hash(announced, app, aspect) != packet.destination_hash:
                return "announce destination"
        elif kind == "announce":
            return "announce type"
        elif kind == "path-request":
            if packet.destination_hash != path_request or packet.packet_type != RNS.Packet.DATA or len(packet.data) < 16:
                return "path request shape"
        elif kind == "transit":
            peer = peer_destinations.get(packet.destination_hash)
            if packet.header_type != RNS.Packet.HEADER_2 or peer is None or peer.decrypt(packet.data) is None:
                return "packet in transport does not decrypt"
        elif kind == "local":
            if packet.destination_hash != station_destination or station.decrypt(packet.data) is None:
                return "packet for the station does not decrypt"
        elif kind == "link-request":
            if packet.packet_type != RNS.Packet.LINKREQUEST or len(packet.data) not in (64, 67) or \
                    len(RNS.Link.link_id_from_lr_packet(packet)) != 16:
                return "link request shape"
        elif kind == "station-proof":
            proved, signature = packet.data[:32], packet.data[32:]
            if packet.packet_type != RNS.Packet.PROOF or packet.destination_hash != proved[:16] or \
                    not any(peer.validate(signature, proved) for peer in peers):
                return "proof of a station packet"
        elif kind != "announce":
            return "unknown kind"
        return None

    checked, too_far, over_mtu, kinds, problems = 0, 0, 0, {}, []
    for record in records:
        if record["mutated"]:
            continue
        raw, wire = bytes.fromhex(record["raw"]), bytes.fromhex(record["wire"])
        valid, unmasked = RNS.Transport.handle_ifac(wire, interface)
        if len(raw) > RNS.Reticulum.MTU:   # ponad MTU: generator daje kod IFAC losowy, stacja ma odrzucić
            over_mtu += 1
            if valid:
                problems.append({"kind": record["kind"], "problem": "datagram over the MTU passes IFAC", "raw": record["raw"]})
            continue
        checked += 1
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1
        packet = RNS.Packet(None, raw)
        unpacked = packet.unpack()
        if not valid or unmasked != raw:
            what = "IFAC"
        elif raw[1] >= RNS.Transport.PATHFINDER_M:   # Packet.unpack: "Invalid hop count" (RNS/Packet.py:250)
            too_far += 1
            what = "packet with too many hops accepted" if unpacked else None
        else:
            what = problem(record, packet) if unpacked else "unpack"
        if what:
            problems.append({"kind": record["kind"], "problem": what, "raw": record["raw"]})
    return {"records": len(records), "checked": checked, "too_many_hops": too_far, "over_mtu": over_mtu, "kinds": kinds,
            "problems": problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", help="tests/native/rnscore_check built by tests/test_rnscore.py")
    parser.add_argument("--stress-dump", help="dump of tests/native/rns_stress --dump: check the generator traffic only")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mutations", type=int, default=64)
    parser.add_argument("--interfaces", type=int, choices=(1, 2), default=1, help="2: second interface (USB, stage R4)")
    args = parser.parse_args()
    if args.stress_dump:
        result = stress_dump(args.stress_dump)
        print(json.dumps({"reticulum": "e40191b", **result}))
        sys.stdout.flush()
        os._exit(0 if not result["problems"] else 1)
    if not args.check:
        parser.error("--check or --stress-dump is required")
    two = args.interfaces == 2

    core = Core(args.check)
    builder = Builder(core)
    station_key = key("wici differential station")
    steps, dests, station_address = scenario(builder, station_key, random.Random(args.seed), args.mutations, args.interfaces)
    station_identity = builder.identity(station_key)

    # Rdzeń: cała sekwencja naraz na zegarze wirtualnym; po każdym kroku pakiety i trasy.
    commands = [("t_begin", station_key + (b"\x02" if two else b""))]
    sizes = []
    now = 1000
    for kind, value, *on in steps:
        if kind == "in":
            commands.append(("t_inif", bytes(on) + value) if two else ("t_in", value))
            ticks = 1
        else:
            ticks = 0
            for at in range(now + LOOP_MS, now + value + 1, LOOP_MS):
                commands.append(("t_clock", at.to_bytes(8, "big")))
                ticks += 1
            now += value
        commands.append(("t_outif", b"") if two else ("t_out", b""))
        commands += [("t_known", dest) for dest in dests]
        if two:
            commands += [("t_route", dest) for dest in dests]
        tail = 1 + len(dests) * (2 if two else 1)
        sizes.append(ticks + tail)
    lines = core.ask(commands)[1:]
    core_results = []
    at = 0
    for size in sizes:
        chunk = lines[at + size - tail:at + size]
        at += size
        if chunk[0] == "-":
            sent = []
        elif two:
            sent = [(int(x.split(":")[0]), bytes.fromhex(x.split(":")[1])) for x in chunk[0].split()]
        else:
            sent = [(0, bytes.fromhex(x)) for x in chunk[0].split()]
        known = chunk[1:1 + len(dests)]
        core_results.append((sent, core_paths(known, dests, chunk[1 + len(dests):] if two else None)))

    RNS, capture, destination, settle = start_python(station_key, args.interfaces)
    if destination.hash != station_address:
        raise RuntimeError("station address differs between the core and Reticulum")
    capture.take()
    differences = []
    python_segment, core_segment = [], []
    for i, (kind, value, *on) in enumerate(steps):
        if kind == "in":
            RNS.Transport.inbound(value, capture.interfaces[on[0]])
            settle()
        else:
            time.sleep(value / 1000)
            settle()
        python_segment += capture.take()
        python_path = python_paths(RNS, dests, capture)
        core_sent, core_path = core_results[i]
        core_segment += core_sent
        step = {"step": i, "kind": kind, "input": f"{on[0]}:{value.hex()}" if kind == "in" else value}
        if kind == "wait":
            if normalized(python_segment, station_address, station_identity) != normalized(core_segment, station_address,
                                                                                          station_identity):
                differences.append({**step, "python_sent": [f"{n}:{x.hex()}" for n, x in python_segment],
                                    "core_sent": [f"{n}:{x.hex()}" for n, x in core_segment]})
            python_segment, core_segment = [], []
        if python_path != core_path:
            differences.append({**step, "python_paths": python_path, "core_paths": core_path})

    # Jeden wiersz na końcu (Reticulum pisze dziennik na standardowe wyjście).
    print(json.dumps({"reticulum": "e40191b", "seed": args.seed, "interfaces": args.interfaces, "steps": len(steps),
                      "differences": differences}))
    sys.stdout.flush()
    os._exit(0 if not differences else 1)


if __name__ == "__main__":
    main()
