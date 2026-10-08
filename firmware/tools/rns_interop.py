# SPDX-License-Identifier: MIT
"""Compatibility trial of the station stack with reference Reticulum (Python) without a radio.

The station node runs as the "host" PlatformIO program (firmware/src/host/node_host.cpp): the same
microReticulum port, P1 interface, IFAC and FRAM tables as the bench-a image, with an emulated P1 link
(P1 frames, air time, silence debt) bridged over UDP to a UDPInterface of Reticulum in this process.
Both sides use the same 16 B network key as IFAC (passphrase = 32 hex digits, ifac_size = 128 bits).

Checks: station announce seen in Python; Python announce seen in the station; opportunistic packet
in both directions with a transport proof (PacketReceipt DELIVERED on both sides); a packet the
station application layer rejects gets no proof (PROVE_APP), so the Python receipt fails; after a restart
of the station program with the same FRAM file the identity is the same and the path and identity of
the Python destination come from FRAM; datagrams without IFAC or with a wrong IFAC are dropped before
the stack; with the Python destination pinned as the OSP and the tables limited to 6 entries, further
announces evict the oldest unprotected destination and never the OSP.

With --fill N, after the checks Python announces N further destinations through the same link, the
station fills its packet hash list to 4096 entries, and the station status (path table, TLSF pool
peak, FRAM file system use) is recorded as the RAM measurement with full tables (README, "Stos Reticulum").

Run with a Python that has Reticulum at the pinned commit (e40191b), for example:
  python3 -m venv .venv-rns && .venv-rns/bin/pip install "git+https://github.com/markqvist/Reticulum@e40191b"
  .venv-rns/bin/python firmware/tools/rns_interop.py --program firmware/.pio/build/host/program
Prints one JSON object with the results; exit code 0 when every check passed.
"""

import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME = "wici"
ASPECT = "sa1"
NETWORK_KEY = "5749434954335f696661635f74657374"  # 16 B test key, not a field key
TABLE_MAX = 256    # RNS_PATH_TABLE_MAX obrazu (platformio.ini)
PINNED_TABLE = 6   # limit tablic w próbie ochrony wpisu OSP (krok 7)


def log(text):
    print(f"[interop] {text}", file=sys.stderr, flush=True)


class Station:
    """The host program with line JSON events."""

    def __init__(self, program, fram, listen, peer, debt, capture=None, table_max=0, osp=None):
        extra = ["--capture", capture] if capture else []
        extra += ["--table-max", str(table_max)] if table_max else []
        extra += ["--osp", osp] if osp else []   # jak stacja z konfiguracją OSP: przypięcie przed startem stosu
        self.proc = subprocess.Popen([program, "--fram", fram, "--ifac", NETWORK_KEY, "--listen", str(listen),
                                      "--peer", str(peer), "--debt", str(debt)] + extra,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.ready = self.wait("ready", 20)

    def _read(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    self.events.put(json.loads(line))
                except json.JSONDecodeError:
                    pass

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
    parser.add_argument("--port", type=int, default=47420)
    parser.add_argument("--fill", type=int, default=0, help="announce N more destinations and record the station memory")
    parser.add_argument("--capture", help="file for the datagrams Python sends to the station (tools/rns_ram32.py replays them)")
    args = parser.parse_args()

    import RNS  # noqa: E402 (needs the reference Reticulum)

    work = tempfile.mkdtemp(prefix="wici_rns_")
    fram = os.path.join(work, "fram.bin")
    station_port, python_port = args.port, args.port + 1
    config = f"""
[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = Yes

[logging]
  loglevel = 2

[interfaces]
  [[P1 bridge]]
    type = UDPInterface
    enabled = Yes
    listen_ip = 127.0.0.1
    listen_port = {python_port}
    forward_ip = 127.0.0.1
    forward_port = {station_port}
    passphrase = {NETWORK_KEY}
    ifac_size = 128
"""
    os.makedirs(os.path.join(work, "rns"))
    with open(os.path.join(work, "rns", "config"), "w") as f:
        f.write(config)
    RNS.Reticulum(os.path.join(work, "rns"))

    results = {"reticulum": "e40191b", "debt_factor": args.debt, "checks": {}}
    checks = results["checks"]
    seen = {"announces": [], "packets": []}

    identity = RNS.Identity()
    destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    destination.set_proof_strategy(RNS.Destination.PROVE_ALL)
    destination.set_packet_callback(lambda data, packet: seen["packets"].append((time.time(), data)))

    class Announces:
        aspect_filter = f"{APP_NAME}.{ASPECT}"

        def received_announce(self, destination_hash, announced_identity, app_data):
            seen["announces"].append((time.time(), destination_hash, announced_identity, app_data))

    RNS.Transport.register_announce_handler(Announces())

    def wait_for(condition, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False

    station = Station(args.program, fram, station_port, python_port, args.debt, args.capture)
    try:
        if not station.ready:
            raise RuntimeError("station program did not start")
        address = bytes.fromhex(station.ready["address"])
        results["station_address"] = station.ready["address"]
        results["station_identity"] = station.ready["identity"]
        results["declared_bitrate"] = station.ready["bitrate"]

        # 1. Ogłoszenie stacji widoczne w Pythonie.
        station.command("announce 57494349")
        t_announce = time.time()
        checks["station_announce_in_python"] = wait_for(lambda: any(a[1] == address for a in seen["announces"]), 60)
        station_identity = next((a[2] for a in seen["announces"] if a[1] == address), None)
        results["station_app_data"] = next((a[3].hex() for a in seen["announces"] if a[1] == address and a[3]), "")

        # 2. Ogłoszenie z Pythona widoczne w stacji.
        destination.announce(app_data=b"OSP")
        e = station.wait("announce", 60, lambda e: e["dest"] == destination.hash.hex())
        checks["python_announce_in_station"] = e is not None

        # 3. Pakiet okazjonalny stacja -> Python z potwierdzeniem transportowym.
        payload = b'["WICI",1,"interop","station to python"]'
        station.command(f"send {destination.hash.hex()} {payload.hex()} 120")
        sent = station.wait("sent", 10)
        handle = sent["handle"] if sent else 0
        checks["station_packet_accepted"] = handle > 0
        checks["station_to_python_packet"] = wait_for(lambda: any(p[1] == payload for p in seen["packets"]), 90)
        t_packet = next((p[0] for p in seen["packets"] if p[1] == payload), None)
        receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
        checks["station_receipt_delivered"] = bool(receipt and receipt["delivered"])
        if t_packet:
            results["announce_to_packet_s"] = round(t_packet - t_announce, 2)

        # 4. Pakiet okazjonalny Python -> stacja z potwierdzeniem transportowym.
        if station_identity is not None:
            out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            back = b'["WICI",1,"interop","python to station"]'
            t0 = time.time()
            r = RNS.Packet(out, back).send()
            if r:
                # Domyślny limit potwierdzenia Reticulum dla 1 skoku przez szybki interfejs; dług ciszy P1
                # po datagramie 600 B (17,7 s) go przekracza (F02), więc próba ustawia 120 s.
                results["python_default_receipt_timeout_s"] = round(r.timeout, 2)
                r.set_timeout(120)
            e = station.wait("packet", 90, lambda e: e["data"] == back.hex())
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
        if station_identity is not None:
            station.command("accept 0")
            station.wait("accept", 5)
            rejected = b'["WICI",1,"interop","rejected by the station"]'
            r = RNS.Packet(out, rejected).send()
            if r:
                r.set_timeout(45)
            e = station.wait("packet", 60, lambda e: e["data"] == rejected.hex())
            failed = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.FAILED, 60)
            checks["rejected_packet_without_proof"] = e is not None and not e["accepted"] and failed
            station.command("accept 1")
            station.wait("accept", 5)
        else:
            checks["rejected_packet_without_proof"] = False

        # 5. IFAC: datagram bez kodu i z błędnym kodem odrzucony przed stosem.
        before = station.status()
        raw = bytes([0x00, 0x00]) + destination.hash + bytes([0x00]) + b"no ifac"
        wrong = bytes([0x80, 0x00]) + bytes(16) + destination.hash + bytes([0x00]) + b"wrong ifac"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(raw, ("127.0.0.1", station_port))
            s.sendto(wrong, ("127.0.0.1", station_port))
        time.sleep(1.0)
        after = station.status()
        checks["ifac_missing_dropped"] = after["ifac_missing"] == before["ifac_missing"] + 1
        checks["ifac_invalid_dropped"] = after["ifac_invalid"] == before["ifac_invalid"] + 1
        results["station_status"] = after

        if args.fill:
            # Pomiar pamięci: N ogłoszeń nowych celów (po 2 na sekundę, bez wyzwalania ograniczeń
            # napływu ogłoszeń), potem lista skrótów pakietów dopełniona do 4096.
            # Cel Pythona jako OSP: zostaje w pełnej tablicy, więc krok 6 sprawdza jego trasę z FRAM.
            station.command(f"osp {destination.hash.hex()}")
            station.wait("osp", 5)
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

    # 6. Restart stacji z tym samym plikiem FRAM (cel Pythona jako OSP z konfiguracji): tożsamość
    # i trasa z FRAM, tablica tras w limicie także po wczytaniu.
    station = Station(args.program, fram, station_port, python_port, args.debt, osp=destination.hash.hex())
    try:
        ready = station.ready or {}
        checks["identity_restored"] = ready.get("identity") == results.get("station_identity") and not ready.get("identity_new", True)
        checks["table_limit_after_restart"] = ready.get("paths", TABLE_MAX + 1) <= TABLE_MAX
        station.command(f"path {destination.hash.hex()}")
        p = station.wait("path", 5)
        checks["path_and_identity_restored"] = bool(p and p["known"] and p["path"])
        results["paths_after_restart"] = ready.get("paths")
        payload2 = b'["WICI",1,"interop","after restart"]'
        station.command(f"send {destination.hash.hex()} {payload2.hex()} 120")
        sent = station.wait("sent", 10)
        handle = sent["handle"] if sent else 0
        checks["send_after_restart_without_announce"] = handle > 0 and wait_for(
            lambda: any(p[1] == payload2 for p in seen["packets"]), 90)
        receipt = station.wait("receipt", 120, lambda e: e["handle"] == handle) if handle else None
        checks["receipt_after_restart"] = bool(receipt and receipt["delivered"])
    finally:
        station.stop()

    # 7. Pełne tablice: wpis przypiętej OSP zostaje (oprogramowanie.md, „Pojemności stosu”). Nowa
    # pamięć FRAM i limit tablic 6 zamiast 256: cel Pythona jako OSP, potem cel bez ochrony
    # i 8 kolejnych; usunięty ma być najstarszy cel bez ochrony, a nie OSP.
    station = Station(args.program, os.path.join(work, "fram_pinned.bin"), station_port, python_port, args.debt,
                      table_max=PINNED_TABLE)
    try:
        station.command(f"osp {destination.hash.hex()}")
        station.wait("osp", 5)
        destination.announce()
        osp_learned = station.wait("announce", 30, lambda e: e["dest"] == destination.hash.hex()) is not None
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
        osp = station.wait("path", 5) or {}
        station.command(f"path {victim.hash.hex()}")
        gone = station.wait("path", 5) or {}
        results["pinned_table"] = {"limit": PINNED_TABLE, "paths": status.get("paths"), "osp": osp, "unprotected": gone}
        checks["osp_entry_kept_in_full_table"] = (osp_learned and status.get("paths", 99) <= PINNED_TABLE
                                                  and osp.get("known") is True and osp.get("path") is True
                                                  and gone.get("path") is False)
    finally:
        station.stop()

    results["passed"] = all(checks.values())
    print(json.dumps(results, indent=2, default=str))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
