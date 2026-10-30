# SPDX-License-Identifier: MIT
"""Compatibility trial of the station stack with reference Reticulum (Python) without a radio.

The station node runs as the "host-port" PlatformIO program (firmware/src/host/node_host.cpp): the same
microReticulum port, P1 interface, IFAC and FRAM tables as the bench-a-port image, with an emulated P1 link
(P1 frames, air time, silence debt) bridged over UDP to a UDPInterface of Reticulum in this process.
Both sides use the same 16 B network key as IFAC (passphrase = 32 hex digits, ifac_size = 128 bits).

Checks: station announce seen in Python; Python announce seen in the station; opportunistic packet
in both directions with a transport proof (PacketReceipt DELIVERED on both sides), also to a Python
destination that enforces ratchets (step 3r, only with --steps: the station encrypts to the ratchet
key from its announce, which the microReticulum port does not do); path requests in both directions
(step 9, only with --steps: Python asks for the station destination and gets a path response, the
station asks for a Python destination it has never heard and learns its path); a packet the
station application layer rejects gets no proof (PROVE_APP), so the Python receipt fails; after a restart
of the station program with the same FRAM file the identity is the same and the path and identity of
the Python destination come from FRAM; datagrams without IFAC or with a wrong IFAC are dropped before
the stack; with the Python destination pinned as the receiver from the card and the tables limited to 6 entries, further
announces evict the oldest unprotected destination and never the receiver. Step 8 sends to a receiver known only from its card key, in silence with the exception.

With --fill N, after the checks Python announces N further destinations through the same link, the
station fills its packet hash list to 4096 entries, and the station status (path table, TLSF pool
peak, FRAM file system use) is recorded as the RAM measurement with full tables (README, "Stos Reticulum").

Run with a Python that has Reticulum at the pinned commit (e40191b), for example:
  python3 -m venv .venv-rns && .venv-rns/bin/pip install "git+https://github.com/markqvist/Reticulum@e40191b"
  .venv-rns/bin/python firmware/tools/rns_interop.py --program firmware/.pio/build/host-port/program
With --steps (for example 1,5) only the listed steps run: the station core program ("host" since stage R6-3,
firmware/reticulum-core.md) runs the steps its stage already has (tests/test_rns_stack.py).

With --lxmf (station core from stage R3) the station destination is "lxmf.delivery": the Python
destinations use that name, the station sends the stand-in envelope of the station application layer
(["WICI",1,from,to,<SA1>]) and the core carries the SA1 part as an LXMF message, Python sends LXMF SA1
messages to the station (the station application layer gets them back in the envelope), and every
check compares the SA1 content. Steps L1 and L2 exchange SA1 messages with LXMRouter (LXMF c3ff2d6)
in both directions with delivery proofs; L1 also checks the display name in the station announce.
--lxmf needs LXMF at c3ff2d6 in the same Python (pip install "git+https://github.com/markqvist/LXMF@c3ff2d6").

With --link lora (host and host-port) the station runs its LoRa link (node_host --link lora) and Reticulum in
Python uses an RNodeInterface (same IFAC) on the pseudo-terminal of tools/rnode_emulator.py, which turns packets
into on-air frames of the RNode firmware and exchanges them over UDP with the station. Default steps are 1-5 and:
B (datagrams of 508 B, two frames, announces and packets with proof in both directions), J (a 509 B frame pair
injected over UDP is rejected and counted: an RNode does not send over 508 B), D (silence debt 12t between two
packets of the station). Steps 1-5 inject their datagrams as on-air frames. The emulator and the station frame
come from the same reading of the RNode source: this proves interworking with RNodeInterface, not over-the-air
conformance with real firmware (the hardware trial).

Prints one JSON object with the results; exit code 0 when every check passed.
"""

import argparse
import atexit
import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

import rnode_framing   # tools/rnode_framing.py: wzorzec ramki RNode

APP_NAME = "wici"
ASPECT = "sa1"
NETWORK_KEY = "5749434954335f696661635f74657374"  # 16 B test key, not a field key
TABLE_MAX = 256    # RNS_PATH_TABLE_MAX obrazu (platformio.ini)
PINNED_TABLE = 6   # limit tablic w próbie ochrony wpisu odbiorcy (krok 7)
LORA_STEPS = {"1", "2", "3", "4", "5", "B", "J", "D"}   # domyślne kroki z --link lora
LORA_HZ = 869525000   # profil LoRa pilotażu (lora_profile.h): 869,525 MHz, 125 kHz, SF7, CR 4/5, 13 dBm
MAX_DATAGRAM = 508    # HW_MTU RNodeInterface: pakiet z IFAC 16 B
MAX_RAW = MAX_DATAGRAM - 16
OWN_ANNOUNCE_APP_DATA = 316   # najwięcej danych aplikacji we własnym ogłoszeniu stacji (ogłoszenie 483 B + IFAC 16 B)
OWN_ANNOUNCE_BYTES = 499   # to ogłoszenie w eterze: ponad FIRST_FRAME_DATA, więc w dwóch ramkach
FIRST_FRAME_DATA = 254   # dane w pierwszej ramce RNode: ponad tyle datagram idzie w dwóch ramkach


def log(text):
    print(f"[interop] {text}", file=sys.stderr, flush=True)


class Station:
    """The host program with line JSON events."""

    def __init__(self, program, fram, listen, peer, debt, capture=None, table_max=0, receiver=None, link="p1"):
        # Z --link lora także ślad: nadany datagram ("tx": długość, czas, dług) i odebrana ramka ("rx": długość).
        extra = ["--link", "lora", "--trace"] if link == "lora" else []
        extra += ["--capture", capture] if capture else []
        extra += ["--table-max", str(table_max)] if table_max else []
        extra += ["--receiver", receiver] if receiver else []   # jak stacja z kartą odbiorcy: przypięcie przed startem stosu
        self.proc = subprocess.Popen([program, "--fram", fram, "--ifac", NETWORK_KEY, "--listen", str(listen),
                                      "--peer", str(peer), "--debt", str(debt)] + extra,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.events = queue.Queue()
        self.air = []   # zdarzenia "tx" (datagram nadany) i "rx" (ramka odebrana) ze śladu --trace, z czasem odbioru
        threading.Thread(target=self._read, daemon=True).start()
        self.ready = self.wait("ready", 20)

    def _read(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") in ("tx", "rx"):
                    event["time"] = time.time()
                    self.air.append(event)
                self.events.put(event)

    def command(self, text):
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def wait(self, event, timeout, predicate=None):
        end = time.time() + timeout
        while time.time() < end:
            try:
                e = self.events.get(timeout=max(0.05, end - time.time()))
            except queue.Empty:
                break
            if e.get("event") == event and (predicate is None or predicate(e)):
                return e
        return None

    def status(self):
        self.command("status")
        return self.wait("status", 5)

    def stop(self):
        try:
            self.command("quit")
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--debt", type=int, default=12, help="silence debt factor of the emulated P1 link")
    parser.add_argument("--port", type=int, help="first of two UDP ports (default: two free ports from the system)")
    parser.add_argument("--fill", type=int, default=0, help="announce N more destinations and record the station memory")
    parser.add_argument("--capture", help="file for the datagrams Python sends to the station (tools/rns_ram32.py replays them)")
    parser.add_argument("--steps", help="comma-separated steps to run (1,2,3,3r,4,4a,5,6,7,8,9,L1,L2, and B, J, D with --link lora; default all but 3r, 9, L1 and "
                                        "L2 and the LoRa steps; with --link lora 1-5, B, J, D), e.g. for a stack that does not have every function yet (core, firmware/reticulum-core.md)")
    parser.add_argument("--link", choices=("p1", "lora"), default="p1",
                        help="link of the station: emulated P1, or LoRa through the RNode emulator and an RNodeInterface")
    parser.add_argument("--lxmf", action="store_true", help="station destination lxmf.delivery with LXMF SA1 messages (core, stage R3)")
    args = parser.parse_args()
    steps = set(args.steps.split(",")) if args.steps else None
    global APP_NAME, ASPECT
    if args.lxmf:
        APP_NAME, ASPECT = "lxmf", "delivery"

    def want(step):
        # Krok 3r tylko na żądanie: port microReticulum nie szyfruje do ratchetu z ogłoszenia (cel Pythona
        # z wymuszonymi ratchetami odrzuca jego pakiet), więc nie należy do domyślnej próby portu.
        # Krok 9 (zapytania o trasę) też na żądanie: dodany z etapem R2 rdzenia; port przechodzi go lokalnie, ale
        # domyślna próba portu zostaje bez zmian.
        if steps is not None:
            return step in steps
        return step in LORA_STEPS if args.link == "lora" else step not in ("3r", "9", "L1", "L2", "B", "J", "D")

    import RNS  # noqa: E402 (needs the reference Reticulum)
    import udp_ports  # noqa: E402 (tools/udp_ports.py)
    import sa1_lxmf  # noqa: E402 (tools/sa1_lxmf.py)
    if args.lxmf:
        import LXMF  # noqa: E402 (LXMF at c3ff2d6)

    work = tempfile.mkdtemp(prefix="wici_rns_")
    fram = os.path.join(work, "fram.bin")
    station_port, python_port = (args.port, args.port + 1) if args.port else udp_ports.free_udp_ports(2)
    lora = args.link == "lora"
    emulator = None
    if lora:
        # Radio RNode: pseudoterminal, który RNodeInterface otwiera jak port szeregowy; ramki w eterze idą UDP do stacji.
        emulator = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "rnode_emulator.py"),
                                     "--listen", str(python_port), "--peer", str(station_port)],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        # Po wyjściu z Reticulum (jego procedura wyjścia wysyła do radia polecenie "leave"): atexit idzie od końca.
        atexit.register(lambda: (emulator.stdin.close(), emulator.wait(5)))
        python_pty = json.loads(emulator.stdout.readline())["pty"]
    interface = f"""  [[LoRa RNode]]
    type = RNodeInterface
    enabled = Yes
    port = {python_pty if lora else ""}
    frequency = {LORA_HZ}
    bandwidth = 125000
    txpower = 13
    spreadingfactor = 7
    codingrate = 5
    flow_control = No
    passphrase = {NETWORK_KEY}
    ifac_size = 128
""" if lora else f"""  [[P1 bridge]]
    type = UDPInterface
    enabled = Yes
    listen_ip = 127.0.0.1
    listen_port = {python_port}
    forward_ip = 127.0.0.1
    forward_port = {station_port}
    passphrase = {NETWORK_KEY}
    ifac_size = 128
"""
    config = f"""
[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = Yes

[logging]
  loglevel = 2

[interfaces]
{interface}"""
    os.makedirs(os.path.join(work, "rns"))
    with open(os.path.join(work, "rns", "config"), "w") as f:
        f.write(config)
    RNS.Reticulum(os.path.join(work, "rns"), logdest=lambda line: print(line, file=sys.stderr, flush=True))

    results = {"reticulum": "e40191b", "link": args.link, "debt_factor": args.debt, "steps": sorted(steps) if steps else "default", "checks": {}}
    checks = results["checks"]
    seen = {"announces": [], "packets": []}

    identity = RNS.Identity()
    destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    destination.set_proof_strategy(RNS.Destination.PROVE_ALL)
    destination.set_packet_callback(lambda data, packet: seen["packets"].append((time.time(), data, packet.destination_hash)))

    class Announces:
        aspect_filter = f"{APP_NAME}.{ASPECT}"

        def received_announce(self, destination_hash, announced_identity, app_data):
            seen["announces"].append((time.time(), destination_hash, announced_identity, app_data))

    RNS.Transport.register_announce_handler(Announces())

    class PathResponses:
        # Odpowiedzi na zapytania o trasę (domyślnie nie trafiają do obsługi ogłoszeń).
        aspect_filter = f"{APP_NAME}.{ASPECT}"
        receive_path_responses = True

        def received_announce(self, destination_hash, announced_identity, app_data, announce_packet_hash, is_path_response):
            if is_path_response:
                seen.setdefault("path_responses", []).append((time.time(), destination_hash))

    RNS.Transport.register_announce_handler(PathResponses())

    station_address = None   # cel stacji z jej zdarzenia "ready"

    def outgoing(dest_hash, content):
        # Dane polecenia send: przy --lxmf koperta warstwy aplikacji stacji (station.cpp) z treścią SA1.
        return sa1_lxmf.envelope(station_address, dest_hash, content) if args.lxmf else content

    def carried(packet, content):
        # Pakiet odebrany w Pythonie (czas, dane, cel) niesie dokładnie tę treść: przy --lxmf jako wiadomość
        # LXMF SA1 (LXMessage.unpack_from_bytes ze skrótem celu), bez --lxmf jako całe dane pakietu.
        _, data, dest_hash = packet
        return sa1_lxmf.carried(dest_hash, data, content) if args.lxmf else data == content

    sa1_of = sa1_lxmf.sa1_of   # cel "wici.sa1" tożsamości: tak warstwa aplikacji adresuje odbiorcę z karty

    def enveloped(event, sender, content):
        # Zdarzenie "packet" stacji to dokładnie koperta warstwy aplikacji od nadawcy (przy --lxmf cel
        # "wici.sa1" odbiorcy z karty) z treścią; bez --lxmf całe dane pakietu.
        data = bytes.fromhex(event["data"])
        return data == (sa1_lxmf.envelope(sender, station_address, content) if args.lxmf else content)

    def card(identity, app_hash):
        # Karta odbiorcy w stacji: cel w warstwie aplikacji (przy --lxmf "wici.sa1") i klucz publiczny.
        station.command(f"receiver {app_hash.hex()} {identity.get_public_key().hex()}")
        return station.wait("receiver", 5) is not None

    def incoming(out, content):
        # Dane pakietu Python -> stacja: przy --lxmf wiadomość LXMF SA1 od celu Pythona (LXMessage.pack).
        return sa1_lxmf.packed(out, destination, content) if args.lxmf else content

    def wait_for(condition, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False

    def inject(datagram, frames=None):
        # Datagram wprost do stacji, z pominięciem Pythona: w LoRa jako ramki RNode (nagłówek, podział), w P1 sam datagram;
        # frames: ramki podane wprost.
        if frames is None:
            frames = rnode_framing.rnode_transmit(datagram, 0) if lora else [datagram]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for frame in frames:
                sock.sendto(frame, ("127.0.0.1", station_port))

    station = Station(args.program, fram, station_port, python_port, args.debt, args.capture, link=args.link)
    try:
        if not station.ready:
            raise RuntimeError("station program did not start")
        address = bytes.fromhex(station.ready["address"])
        station_address = address
        results["station_address"] = station.ready["address"]
        results["station_identity"] = station.ready["identity"]
        results["declared_bitrate"] = station.ready["bitrate"]

        station_identity = t_announce = None   # z kroku 1, gdy go wybrano (--steps)

        # 1. Ogłoszenie stacji widoczne w Pythonie.
        if want("1"):
            station.command("announce 57494349")
            t_announce = time.time()
            checks["station_announce_in_python"] = wait_for(lambda: any(a[1] == address for a in seen["announces"]), 60)
            station_identity = next((a[2] for a in seen["announces"] if a[1] == address), None)
            results["station_app_data"] = next((a[3].hex() for a in seen["announces"] if a[1] == address and a[3]), "")

        # 2. Ogłoszenie z Pythona widoczne w stacji.
        if want("2"):
            destination.announce(app_data=b"receiver")
            e = station.wait("announce", 60, lambda e: e["dest"] == destination.hash.hex())
            checks["python_announce_in_station"] = e is not None

        # 3. Pakiet okazjonalny stacja -> Python z potwierdzeniem transportowym.
        if want("3"):
            payload = b'["WICI",1,"interop","station to python"]'
            station.command(f"send {destination.hash.hex()} {outgoing(destination.hash, payload).hex()} 120")
            sent = station.wait("sent", 10)
            handle = sent["handle"] if sent else 0
            checks["station_packet_accepted"] = handle > 0
            checks["station_to_python_packet"] = wait_for(lambda: any(carried(p, payload) for p in seen["packets"]), 90)
            t_packet = next((p[0] for p in seen["packets"] if carried(p, payload)), None)
            receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
            checks["station_receipt_delivered"] = bool(receipt and receipt["delivered"])
            if t_packet and t_announce:
                results["announce_to_packet_s"] = round(t_packet - t_announce, 2)

        # 3r. Szyfrowanie do ratchetu z ogłoszenia: cel Pythona z ratchetami, które wymusza (enforce_ratchets),
        #     przyjmuje tylko pakiet zaszyfrowany do klucza ratchetu z ostatniego ogłoszenia.
        if want("3r"):
            ratchets = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            ratchets.enable_ratchets(os.path.join(work, "ratchets"))
            ratchets.enforce_ratchets()
            ratchets.set_proof_strategy(RNS.Destination.PROVE_ALL)
            ratchets.set_packet_callback(lambda data, packet: seen["packets"].append((time.time(), data, packet.destination_hash)))
            ratchets.announce(app_data=b"ratchets")
            learned = station.wait("announce", 60, lambda e: e["dest"] == ratchets.hash.hex()) is not None
            to_ratchet = b'["WICI",1,"interop","to a ratchet"]'
            station.command(f"send {ratchets.hash.hex()} {outgoing(ratchets.hash, to_ratchet).hex()} 120")
            sent = station.wait("sent", 10)
            handle = sent["handle"] if sent else 0
            checks["ratchet_packet_decrypted"] = learned and handle > 0 and wait_for(
                lambda: any(carried(p, to_ratchet) for p in seen["packets"]), 90)
            receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
            checks["ratchet_receipt_delivered"] = bool(receipt and receipt["delivered"])

        # 4. Pakiet okazjonalny Python -> stacja z potwierdzeniem transportowym.
        if want("4"):
            if station_identity is not None:
                out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                if args.lxmf:
                    card(identity, sa1_of(identity))   # rdzeń przyjmuje wiadomości tylko od odbiorcy z karty
                back = b'["WICI",1,"interop","python to station"]'
                t0 = time.time()
                r = RNS.Packet(out, incoming(out, back)).send()
                if r:
                    # Domyślny limit potwierdzenia Reticulum dla 1 skoku przez szybki interfejs; dług ciszy P1
                    # po datagramie 600 B (17,7 s) go przekracza (F02), więc próba ustawia 120 s.
                    results["python_default_receipt_timeout_s"] = round(r.timeout, 2)
                    r.set_timeout(120)
                e = station.wait("packet", 90, lambda e: enveloped(e, sa1_of(identity), back))
                checks["python_to_station_packet"] = e is not None
                checks["python_receipt_delivered"] = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.DELIVERED, 120)
                if r and r.status == RNS.PacketReceipt.DELIVERED:
                    results["python_proof_rtt_s"] = round(r.get_rtt(), 2)
                results["python_to_station_s"] = round(time.time() - t0, 2)
            else:
                checks["python_to_station_packet"] = False
                checks["python_receipt_delivered"] = False

        # 4a. Pakiet odrzucony przez warstwę aplikacji stacji: bez dowodu (PROVE_APP), potwierdzenie
        #     w Pythonie kończy się niepowodzeniem po limicie.
        if want("4a"):
            if station_identity is not None:
                out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                if args.lxmf:
                    card(identity, sa1_of(identity))   # jak w kroku 4: także przy osobnym --steps 4a
                station.command("accept 0")
                station.wait("accept", 5)
                rejected = b'["WICI",1,"interop","rejected by the station"]'
                r = RNS.Packet(out, incoming(out, rejected)).send()
                if r:
                    r.set_timeout(45)
                e = station.wait("packet", 60, lambda e: enveloped(e, sa1_of(identity), rejected))
                failed = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.FAILED, 60)
                checks["rejected_packet_without_proof"] = e is not None and not e["accepted"] and failed
                station.command("accept 1")
                station.wait("accept", 5)
                if args.lxmf:
                    # Trwałe odrzucenie przed warstwą aplikacji (oprogramowanie.md, „Dowód dostarczenia po COMMIT”):
                    # dowód wychodzi, zdarzenia "packet" nie ma, rośnie licznik powodu.
                    def rejected_with_proof(data, counter):
                        before = station.status() or {}
                        r = RNS.Packet(out, bytes(data)).send()
                        if r:
                            r.set_timeout(120)
                        proved = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.DELIVERED, 120)
                        delivered_to_app = station.wait("packet", 2) is not None
                        after = station.status() or {}
                        return (proved and not delivered_to_app and after.get(counter, 0) == before.get(counter, 0) + 1
                                and after.get("lxmf_rejected", 0) == before.get("lxmf_rejected", 0) + 1)

                    other = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                    other.announce()
                    other_known = station.wait("announce", 60, lambda e: e["dest"] == other.hash.hex()) is not None
                    from_other = LXMF.LXMessage(out, other, '[4,"interop","not on the card"]', "SA1",
                                                desired_method=LXMF.LXMessage.OPPORTUNISTIC)
                    from_other.pack()
                    from_other = from_other.packed[16:]
                    bad_signature = bytearray(incoming(out, b'[4,"interop","bad signature"]'))
                    bad_signature[16] ^= 0x01   # pierwszy bajt podpisu
                    stamped = bytearray(incoming(out, b'[4,"interop","stamp"]'))
                    stamped[80] = 0x95          # payload jako tablica 5 elementów: znaczek pracy
                    checks["non_sa1_rejected_with_proof"] = rejected_with_proof(b"not an LXMF message", "lxmf_rej_sender")
                    checks["off_card_sender_rejected"] = other_known and rejected_with_proof(from_other, "lxmf_rej_sender")
                    checks["forged_source_rejected"] = other_known and rejected_with_proof(destination.hash + from_other[16:],
                                                                                           "lxmf_rej_signature")
                    checks["bad_signature_rejected"] = rejected_with_proof(bad_signature, "lxmf_rej_signature")
                    checks["stamp_rejected"] = rejected_with_proof(stamped, "lxmf_rej_stamp")
            else:
                checks["rejected_packet_without_proof"] = False
                if args.lxmf:
                    for name in ("non_sa1_rejected_with_proof", "off_card_sender_rejected", "forged_source_rejected",
                                 "bad_signature_rejected", "stamp_rejected"):
                        checks[name] = False

        # 5. IFAC: datagram bez kodu i z błędnym kodem odrzucony przed stosem.
        if want("5"):
            before = station.status()
            raw = bytes([0x00, 0x00]) + destination.hash + bytes([0x00]) + b"no ifac"
            wrong = bytes([0x80, 0x00]) + bytes(16) + destination.hash + bytes([0x00]) + b"wrong ifac"
            inject(raw)
            inject(wrong)
            time.sleep(1.0)
            after = station.status()
            checks["ifac_missing_dropped"] = after["ifac_missing"] == before["ifac_missing"] + 1
            checks["ifac_invalid_dropped"] = after["ifac_invalid"] == before["ifac_invalid"] + 1
            results["station_status"] = after

        # B. Największe datagramy łącza w dwóch ramkach, w obie strony. Python -> stacja: ogłoszenie z danymi 325 B, czyli
        #    pakiet 492 B i IFAC 16 B = 508 B (dwie ramki po 255 B, RNode dodaje trzecią, 1 B, którą stacja pomija).
        #    Stacja -> Python: własne ogłoszenie stacji z największymi danymi (OWN_ANNOUNCE_APP_DATA), 499 B, i pakiet
        #    z dowodem (ponad 254 B). Wymaga kroków 1 i 2 (trasa celu Pythona).
        if want("B"):
            pad = bytes(i % 251 for i in range(OWN_ANNOUNCE_APP_DATA))
            announce_at = len(station.air)
            station.command(f"announce {pad.hex()}")
            # Python zapamiętuje dane aplikacji z każdego ważnego ogłoszenia (także gdy nie zmienia ono trasy).
            checks["lora_big_announce_to_python"] = wait_for(lambda: RNS.Identity.recall_app_data(address) == pad, 90)
            checks["lora_big_announce_two_frames"] = any(e["event"] == "tx" and e["length"] == OWN_ANNOUNCE_BYTES
                                                          for e in station.air[announce_at:])
            # Python -> stacja: ogłoszenie nowego celu z danymi 325 B (167 B + dane = pakiet 492 B).
            big = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            app_data = bytes(i % 241 for i in range(MAX_RAW - 167))
            rx = len(station.air)
            big.announce(app_data=app_data)
            e = station.wait("announce", 60, lambda e: e["dest"] == big.hash.hex())
            checks["lora_big_announce_to_station"] = e is not None and e["app_data"] == app_data.hex()
            # Trzecia ramka RNode (sam nagłówek, 1 B) idzie za dwiema pełnymi i jest pomijana w stacji.
            checks["lora_big_announce_frames_255"] = [x["length"] for x in station.air[rx:] if x["event"] == "rx"][:3] == [255, 255, 1]
            # Pakiety z dowodem w obie strony (po ok. 220 B treści: ponad 254 B w eterze).
            body = b'["WICI",1,"interop","' + b"x" * 190 + b'"]'
            if station_identity is not None:
                out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                if args.lxmf:
                    card(identity, sa1_of(identity))
                tx = len([x for x in station.air if x["event"] == "tx"])
                station.command(f"send {destination.hash.hex()} {outgoing(destination.hash, body).hex()} 120")
                sent = station.wait("sent", 10)
                handle = sent["handle"] if sent else 0
                checks["lora_big_packet_to_python"] = handle > 0 and wait_for(lambda: any(carried(p, body) for p in seen["packets"]), 120)
                receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
                checks["lora_big_packet_receipt"] = bool(receipt and receipt["delivered"])
                sent_lengths = [x["length"] for x in station.air if x["event"] == "tx"][tx:]
                checks["lora_big_packet_two_frames"] = bool(sent_lengths) and sent_lengths[0] > FIRST_FRAME_DATA
                rx = len(station.air)
                r = RNS.Packet(out, incoming(out, body)).send()
                if r:
                    r.set_timeout(120)
                checks["lora_big_packet_to_station"] = station.wait("packet", 90, lambda e: enveloped(e, sa1_of(identity), body)) is not None
                checks["lora_big_packet_proof"] = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.DELIVERED, 120)
                received = [x["length"] for x in station.air[rx:] if x["event"] == "rx"]
                checks["lora_big_packet_frames_from_python"] = len(received) >= 2 and received[0] == 255
            else:
                for name in ("lora_big_packet_to_python", "lora_big_packet_receipt", "lora_big_packet_two_frames",
                             "lora_big_packet_to_station", "lora_big_packet_proof", "lora_big_packet_frames_from_python"):
                    checks[name] = False

        # J. Para ramek 509 B wstrzyknięta wprost przez UDP (emulator RNode jak RNode nie nada ponad 508 B): druga ramka
        #    ma 256 B, stacja ją odrzuca i liczy, a pierwsza część przepada po 1 s; żaden datagram nie dochodzi do stosu.
        if want("J"):
            before = station.status()
            data = bytes(i % 239 for i in range(MAX_DATAGRAM + 1))
            head = bytes([0x30 | rnode_framing.FLAG_SPLIT])   # ramki ręcznie: RNode pociąłby 509 B na trzy ramki
            inject(None, [head + data[:FIRST_FRAME_DATA], head + data[FIRST_FRAME_DATA:]])
            time.sleep(2.0)
            after = station.status()
            delta = lambda key: after.get(key, 0) - before.get(key, 0)
            results["frames_509"] = {k: delta(k) for k in ("lora_bad_length", "lora_assembly_timeout", "frames_in", "datagrams_in")}
            checks["frames_509_rejected_and_counted"] = (delta("lora_bad_length") == 1 and delta("lora_assembly_timeout") == 1
                                                         and delta("datagrams_in") == 0)

        # D. Dług ciszy: po nadaniu 12t ciszy (t = rezerwacja czasu TX datagramu), więc drugi z dwóch pakietów stacji
        #    zaczyna się najwcześniej po czasie nadawania i długu pierwszego.
        if want("D"):
            settled = len(station.air)
            while True:   # poprzednie nadawania muszą się skończyć razem z długiem (najdłuższy ok. 10 s)
                time.sleep(12)
                if len(station.air) == settled:
                    break
                settled = len(station.air)
            before = len([e for e in station.air if e["event"] == "tx"])
            for text in (b'["WICI",1,"interop","debt one"]', b'["WICI",1,"interop","debt two"]'):
                station.command(f"send {destination.hash.hex()} {outgoing(destination.hash, text).hex()} 120")
                station.wait("sent", 10)
            wait_for(lambda: len([e for e in station.air if e["event"] == "tx"]) >= before + 2, 120)
            sent_air = [e for e in station.air if e["event"] == "tx"][before:before + 2]
            if len(sent_air) == 2:
                gap = sent_air[1]["time"] - sent_air[0]["time"]
                need = (sent_air[0]["air_ms"] + sent_air[0]["debt_ms"]) / 1000
                results["debt_gap_s"] = {"gap": round(gap, 2), "air_plus_debt": round(need, 2), "debt_ms": sent_air[0]["debt_ms"]}
                checks["debt_12t_between_packets"] = gap >= need - 0.2 and sent_air[0]["debt_ms"] >= 12 * sent_air[0]["air_ms"]
            else:
                checks["debt_12t_between_packets"] = False


        # 9. Zapytania o trasę: Python pyta o cel stacji i dostaje odpowiedź stacji (ogłoszenie z kontekstem
        #    PATH_RESPONSE); stacja pyta o cel Pythona, którego ogłoszenia nie słyszała, i poznaje jego trasę
        #    z odpowiedzi Pythona dla celu lokalnego.
        if want("9"):
            # Odpowiedź z czasem emisji (w sekundach) równym ogłoszeniu z kroku 1 nie zmienia trasy w Pythonie
            # (should_add), więc zapytanie dopiero po pełnej sekundzie od niego.
            time.sleep(2)
            RNS.Transport.request_path(address)
            checks["station_answers_path_request"] = wait_for(
                lambda: any(r[1] == address for r in seen.get("path_responses", [])), 60)
            silent = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            station.command(f"path {silent.hash.hex()}")
            before = station.wait("path", 5) or {}
            station.command(f"request {silent.hash.hex()}")
            station.wait("requested", 5)

            def learned():
                station.command(f"path {silent.hash.hex()}")
                p = station.wait("path", 5) or {}
                return p.get("known") is True and p.get("path") is True

            checks["station_path_request_answered"] = before.get("known") is False and wait_for(learned, 60)

        # L1, L2. Wymiana z LXMRouter (LXMF c3ff2d6) w obie strony, tylko z --lxmf; tożsamość stacji z kroku 1.
        #     Tożsamość LXMRouter to odbiorca z karty, a warstwa aplikacji adresuje go celem "wici.sa1" tego
        #     klucza: rdzeń tłumaczy go na cel "lxmf.delivery" i z powrotem (rns_node_core.cpp).
        if args.lxmf and (want("L1") or want("L2")):
            router = LXMF.LXMRouter(storagepath=os.path.join(work, "lxmf"))
            router_identity = RNS.Identity()
            router_destination = router.register_delivery_identity(router_identity, display_name="stanowisko")
            delivered = []
            router.register_delivery_callback(lambda message: delivered.append(message))
            router.announce(router_destination.hash)
            router_learned = station.wait("announce", 60, lambda e: e["dest"] == router_destination.hash.hex()) is not None
            router_card = sa1_of(router_identity)
            router_learned = card(router_identity, router_card) and router_learned

            # L1. Stacja -> LXMRouter: wiadomość SA1 z podpisem stacji, potwierdzenie dostarczenia w stacji;
            #     nazwa wyświetlana z ogłoszenia stacji bez danych aplikacji (WICI-xxxxxx).
            if want("L1"):
                count = len(seen["announces"])
                station.command("announce")
                checks["station_lxmf_announce"] = wait_for(lambda: any(a[1] == address for a in seen["announces"][count:]), 60)
                app_data = next((a[3] for a in seen["announces"][count:] if a[1] == address), None)
                results["station_display_name"] = LXMF.display_name_from_app_data(app_data) if app_data else None
                content = b'[2,"interop","station to LXMRouter"]'
                station.command(f"send {router_card.hex()} {outgoing(router_card, content).hex()} 120")
                sent = station.wait("sent", 10)
                handle = sent["handle"] if sent else 0
                got = wait_for(lambda: any(m.content == content for m in delivered), 90)
                message = next((m for m in delivered if m.content == content), None)
                checks["lxmf_station_to_router"] = (router_learned and handle > 0 and got and message.title == b"SA1"
                                                    and message.signature_validated and message.source_hash == address
                                                    and message.destination_hash == router_destination.hash)
                receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
                checks["lxmf_station_receipt_delivered"] = bool(receipt and receipt["delivered"])

            # L2. LXMRouter -> stacja: warstwa aplikacji dostaje SA1 w kopercie z nadawcą, LXMRouter stan DELIVERED
            #     po dowodzie stacji.
            if want("L2"):
                if station_identity is not None:
                    out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
                    content = b'[3,"interop","LXMRouter to station"]'
                    message = LXMF.LXMessage(out, router_destination, content.decode(), "SA1",
                                             desired_method=LXMF.LXMessage.OPPORTUNISTIC)
                    router.handle_outbound(message)
                    e = station.wait("packet", 90, lambda e: enveloped(e, router_card, content))
                    checks["lxmf_router_to_station"] = router_learned and e is not None
                    checks["lxmf_router_delivered"] = wait_for(lambda: message.state == LXMF.LXMessage.DELIVERED, 120)
                else:
                    checks["lxmf_router_to_station"] = checks["lxmf_router_delivered"] = False

        if args.fill:
            # Pomiar pamięci: N ogłoszeń nowych celów (po 2 na sekundę, bez wyzwalania ograniczeń
            # napływu ogłoszeń), potem lista skrótów pakietów dopełniona do 4096.
            # Cel Pythona jako odbiorca z karty: zostaje w pełnej tablicy, więc krok 6 sprawdza jego trasę z FRAM.
            station.command(f"receiver {destination.hash.hex()}")
            station.wait("receiver", 5)
            fill_destinations = []
            for i in range(args.fill):
                d = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                d.announce(app_data=b"fill%d" % i)
                fill_destinations.append(d)
                time.sleep(0.5)
            target = min(after["paths"] + args.fill, TABLE_MAX)
            end = time.time() + 120
            status = station.status()
            while status and status["paths"] < target and time.time() < end:
                time.sleep(2)
                status = station.status()
            station.command(f"hashes {4096 - status['hashes']}" if status and status["hashes"] < 4096 else "hashes 0")
            station.wait("hashes", 30)
            filled = station.status()
            results["fill"] = {"announced": args.fill, "paths": filled["paths"], "hashes": filled["hashes"],
                               "announce_table": filled["announce_table"], "pool": filled["pool"],
                               "pool_used": filled["pool_used"], "pool_peak": filled["pool_peak"],
                               "fs_files": filled["fs_files"], "fs_used": filled["fs_used"],
                               "fs_capacity": filled["fs_capacity"]}
            checks["fill_paths_complete"] = filled["paths"] >= target
    finally:
        station.stop()

    # 6. Restart stacji z tym samym plikiem FRAM (cel Pythona jako odbiorca z karty): tożsamość
    # i trasa z FRAM, tablica tras w limicie także po wczytaniu.
    if want("6"):
        station = Station(args.program, fram, station_port, python_port, args.debt, receiver=destination.hash.hex(), link=args.link)
        try:
            ready = station.ready or {}
            checks["identity_restored"] = ready.get("identity") == results.get("station_identity") and not ready.get("identity_new", True)
            checks["table_limit_after_restart"] = ready.get("paths", TABLE_MAX + 1) <= TABLE_MAX
            station.command(f"path {destination.hash.hex()}")
            p = station.wait("path", 5)
            checks["path_and_identity_restored"] = bool(p and p["known"] and p["path"])
            results["paths_after_restart"] = ready.get("paths")
            payload2 = b'["WICI",1,"interop","after restart"]'
            station.command(f"send {destination.hash.hex()} {outgoing(destination.hash, payload2).hex()} 120")
            sent = station.wait("sent", 10)
            handle = sent["handle"] if sent else 0
            checks["send_after_restart_without_announce"] = handle > 0 and wait_for(
                lambda: any(carried(p, payload2) for p in seen["packets"]), 90)
            receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
            checks["receipt_after_restart"] = bool(receipt and receipt["delivered"])
        finally:
            station.stop()

    # 7. Pełne tablice: wpis odbiorcy z karty zostaje (oprogramowanie.md, „Pojemności stosu”). Nowa
    # pamięć FRAM i limit tablic 6 zamiast 256: cel Pythona jako odbiorca, potem cel bez ochrony
    # i 8 kolejnych; usunięty ma być najstarszy cel bez ochrony, a nie odbiorca.
    if want("7"):
        station = Station(args.program, os.path.join(work, "fram_pinned.bin"), station_port, python_port, args.debt,
                          table_max=PINNED_TABLE, link=args.link)
        try:
            station.command(f"receiver {destination.hash.hex()}")
            station.wait("receiver", 5)
            destination.announce()
            receiver_learned = station.wait("announce", 30, lambda e: e["dest"] == destination.hash.hex()) is not None
            time.sleep(2)   # znaczniki czasu wpisów w sekundach: cel bez ochrony wyraźnie starszy od reszty
            victim = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            victim.announce()
            station.wait("announce", 30, lambda e: e["dest"] == victim.hash.hex())
            time.sleep(2)
            fillers = []
            for _ in range(PINNED_TABLE + 2):
                d = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
                d.announce()
                fillers.append(d)
                station.wait("announce", 30, lambda e, h=d.hash.hex(): e["dest"] == h)
                time.sleep(0.5)
            status = station.status() or {}
            station.command(f"path {destination.hash.hex()}")
            kept = station.wait("path", 5) or {}
            station.command(f"path {victim.hash.hex()}")
            gone = station.wait("path", 5) or {}
            results["pinned_table"] = {"limit": PINNED_TABLE, "paths": status.get("paths"), "receiver": kept, "unprotected": gone}
            checks["receiver_entry_kept_in_full_table"] = (receiver_learned and status.get("paths", 99) <= PINNED_TABLE
                                                           and kept.get("known") is True and kept.get("path") is True
                                                           and gone.get("path") is False)
        finally:
            station.stop()

    # 8. Tożsamość odbiorcy z klucza karty: wysyłka bez ogłoszenia odbiorcy (nowa pamięć FRAM), w ciszy
    # z wyjątkiem pakiet z send() wychodzi, a ogłoszenie stacji nie.
    if want("8"):
        station = Station(args.program, os.path.join(work, "fram_card.bin"), station_port, python_port, args.debt, link=args.link)
        try:
            # Przy --lxmf karta podaje cel "wici.sa1" klucza, a rdzeń wysyła do jego celu "lxmf.delivery".
            card_hash = sa1_of(identity) if args.lxmf else destination.hash
            key = destination.identity.get_public_key().hex()
            station.command(f"receiver {card_hash.hex()} {key}")
            station.wait("receiver", 5)
            station.command(f"path {card_hash.hex()}")
            known = station.wait("path", 5) or {}
            checks["receiver_known_from_card"] = known.get("known") is True
            station.command("silence exception")
            station.wait("silence", 5)
            station.command("announce")
            silenced = station.wait("announced", 10) or {}
            checks["announce_blocked_in_silence"] = silenced.get("ok") is False
            payload3 = b'["WICI",1,"interop","card key in exception"]'
            station.command(f"send {card_hash.hex()} {outgoing(card_hash, payload3).hex()} 120")
            sent = station.wait("sent", 10)
            handle = sent["handle"] if sent else 0
            checks["send_from_card_key_in_exception"] = handle > 0 and wait_for(
                lambda: any(carried(p, payload3) for p in seen["packets"]), 90)
        finally:
            station.stop()

    results["passed"] = all(checks.values())
    print(json.dumps(results, indent=2, default=str))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
