# SPDX-License-Identifier: MIT
"""Compatibility trial of the OSP node (decision D19) with reference Reticulum (Python), without a radio.

Two station programs (the "host" PlatformIO program, firmware/src/host/node_host.cpp) are joined by the
emulated P1 link over UDP: a station and a station in the OSP node configuration (--node). The node
has the second Reticulum interface over USB; here the USB data port is a pseudo-terminal, and this
process runs reference Reticulum with a KISSInterface (flow control on) on it, as the computer of the
receiving station does (docs/spec/stanowisko-osp.md, "Komputer i aplikacja stanowiska"; radio.md, "Interfejs
Reticulum przez USB"). The computer has transport and network interfaces off; the node forwards.

Checks: the node has no address of its own and does not announce; the computer turns flow control on;
the computer announce reaches the station through the node over P1, and its destination is protected
in the node tables; the station announce reaches the computer; an opportunistic packet in both
directions with a transport proof, the computer receipt time-out set only by the interface bitrate
in the Reticulum config (no set_timeout, no change in the stack code); a burst of packets from the computer passes the KISS flow control
without the 5 s time-out of the Python interface and without drops at the node.

With --lxmf (both programs on the station Reticulum core, "host-core", stage R4b) the station destination
is "lxmf.delivery", the computer is the card receiver of the station, and the packets carry SA1 as LXMF
messages (tools/sa1_lxmf.py), as from a plain LXMF client on the computer. One more check: the computer
destination stays protected after a restart of the node (rebuilt from the routes through USB in FRAM),
and a flood from the computer side (announces with a bad signature and KISS garbage, written past the
Python interface) during a report from the station: at most one asymmetric operation in a node loop pass,
P1 receive steps still run (interleaved with USB) and the report is delivered with its receipt.

Run with a Python that has Reticulum at the pinned commit (e40191b) and pyserial, for example:
  .venv-rns/bin/python firmware/tools/rns_node.py --program firmware/.pio/build/host/program
Prints one JSON object with the results; exit code 0 when every check passed.
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME = "wici"
ASPECT = "sa1"
NETWORK_KEY = "5749434954335f696661635f74657374"  # 16 B test key, not a field key
BURST = 6
FLOOD_INTERVAL_S = 0.02   # zalew z USB: ramka co 20 ms (ok. 50/s, ponad limit weryfikacji i bufor KISS)


def log(text):
    print(f"[osp-node] {text}", file=sys.stderr, flush=True)


class Program:
    """The host program with line JSON events."""

    def __init__(self, program, fram, listen, peer, debt, node=False):
        extra = ["--node"] if node else []
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
        return self.wait("status", 5) or {}

    def stop(self):
        try:
            self.command("quit")
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def flood(node, station, kiss, results, checks, outgoing, received):
    """Zalew z USB (dowolny laptop podłączony w kryzysie, także zawirusowany) przy ruchu P1: ogłoszenia
    z błędnym podpisem (różne cele, więc każde idzie do weryfikacji) i śmieci KISS (ramki ponad 500 B,
    nieznane polecenia, błędne sekwencje, ramki bez końca) zapisywane w port szeregowy obok interfejsu
    Reticulum. W tym czasie zgłoszenie stacji przez węzeł do komputera z potwierdzeniem."""
    import RNS
    from RNS.Interfaces.KISSInterface import KISS

    def frame(data, command=0x00):
        return bytes([KISS.FEND, command]) + KISS.escape(data) + bytes([KISS.FEND])

    name_hash = RNS.Identity.full_hash(b"lxmf.delivery")[:10]
    garbage = [frame(os.urandom(600)), bytes([KISS.FEND, 0x07]) + os.urandom(20) + bytes([KISS.FEND]),
               bytes([KISS.FEND, 0x00, KISS.FESC, 0x41, KISS.FEND]), bytes([KISS.FEND, 0x00]) + os.urandom(40)]
    stop = threading.Event()
    sent = {"announces": 0, "garbage": 0}

    def run():
        n = 0
        while not stop.is_set():
            if n % 3 == 2:
                kiss.serial.write(garbage[n % len(garbage)])
                sent["garbage"] += 1
            else:
                identity = RNS.Identity()
                dest = RNS.Destination.hash(identity, "lxmf", "delivery")
                announce = bytes([0x01, 0x00]) + dest + bytes([0x00]) + identity.get_public_key() + name_hash + os.urandom(10) + os.urandom(64)
                kiss.serial.write(frame(announce))
                sent["announces"] += 1
            n += 1
            time.sleep(FLOOD_INTERVAL_S)

    before = node.status()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(5)   # zalew trwa, zanim stacja wyśle zgłoszenie
    content = b'["WICI",1,"osp node","report during a USB flood"]'
    data, target = outgoing(content)
    t0 = time.time()
    station.command(f"send {target.hex()} {data.hex()} 120")
    sent_event = station.wait("sent", 10)
    handle = sent_event["handle"] if sent_event else 0
    got = handle > 0 and received(content)
    receipt = station.wait("receipt", 240, lambda e: e["handle"] == handle) if handle else None
    stop.set()
    thread.join()
    after = node.status()
    delta = lambda key: after.get(key, 0) - before.get(key, 0)
    results["flood"] = {"seconds": round(time.time() - t0, 2), "announces": sent["announces"], "garbage": sent["garbage"],
                        "usb_rns_in": delta("usb_rns_in"), "usb_rx_drop": delta("usb_rx_drop"), "usb_rx_large": delta("usb_rx_large"),
                        "usb_ann_limited": delta("usb_ann_limited"), "rx_invalid": delta("rx_invalid"), "p1_rx_ok": delta("rx_ok"),
                        "loop_ops_max": after.get("loop_ops_max")}
    checks["flood_report_delivered"] = bool(got and receipt and receipt["delivered"])
    checks["flood_one_operation_per_loop"] = after.get("loop_ops_max") == 1
    # Kroki P1 w węźle w trakcie zalewu (zgłoszenie i dowód przez P1) i limit weryfikacji ogłoszeń z USB.
    checks["flood_p1_steps_run"] = delta("rx_ok") >= 2
    checks["flood_usb_announces_limited"] = delta("usb_ann_limited") > 0 and delta("rx_invalid") > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--debt", type=int, default=12, help="silence debt factor of the emulated P1 link")
    parser.add_argument("--port", type=int, default=47440)
    parser.add_argument("--lxmf", action="store_true", help="station core: lxmf.delivery and LXMF SA1 messages (stage R4b)")
    parser.add_argument("--bitrate", type=int, default=24,
                        help="bitrate of the computer KISS interface in the Reticulum config (bit/s); it sets the receipt "
                             "timeouts: 500 B x 8 / bitrate + 6 s + 6 s per hop")
    args = parser.parse_args()
    global APP_NAME, ASPECT
    if args.lxmf:
        APP_NAME, ASPECT = "lxmf", "delivery"

    import RNS  # noqa: E402 (needs the reference Reticulum)
    import sa1_lxmf  # noqa: E402 (tools/sa1_lxmf.py)

    work = tempfile.mkdtemp(prefix="wici_osp_node_")
    station_port, node_port = args.port, args.port + 1
    results = {"reticulum": "e40191b", "debt_factor": args.debt, "bitrate": args.bitrate, "checks": {}}
    checks = results["checks"]
    node_fram = os.path.join(work, "node.bin")
    node = Program(args.program, node_fram, node_port, station_port, args.debt, node=True)
    station = Program(args.program, os.path.join(work, "station.bin"), station_port, node_port, args.debt)
    try:
        if not node.ready or not station.ready:
            raise RuntimeError("host programs did not start")
        pty = node.ready["usb"]
        station_address = bytes.fromhex(station.ready["address"])
        checks["node_without_address"] = node.ready["node"] is True and node.ready["address"] == "0" * 32
        node.command("announce")
        e = node.wait("announced", 5)
        checks["node_does_not_announce"] = e is not None and e["ok"] is False

        config = f"""
[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = Yes

[logging]
  loglevel = 2

[interfaces]
  [[OSP station]]
    type = KISSInterface
    enabled = Yes
    port = {pty}
    speed = 115200
    flow_control = Yes
    bitrate = {args.bitrate}
"""
        os.makedirs(os.path.join(work, "rns"))
        with open(os.path.join(work, "rns", "config"), "w") as f:
            f.write(config)
        # Dziennik Reticulum na stderr: na stdout tylko wynik JSON (test go parsuje).
        RNS.Reticulum(os.path.join(work, "rns"), logdest=lambda line: print(line, file=sys.stderr, flush=True))
        kiss = next(i for i in RNS.Transport.interfaces if type(i).__name__ == "KISSInterface")

        seen = {"announces": [], "packets": []}
        identity = RNS.Identity()
        destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
        destination.set_proof_strategy(RNS.Destination.PROVE_ALL)
        destination.set_packet_callback(lambda data, packet: seen["packets"].append((time.time(), data, packet.destination_hash)))
        computer_sa1 = sa1_lxmf.sa1_of(identity)

        def outgoing(content):
            # Dane polecenia send stacji: przy --lxmf koperta warstwy aplikacji do odbiorcy z karty (komputer).
            return sa1_lxmf.envelope(station_address, computer_sa1, content) if args.lxmf else content

        def carried(packet, content):
            _, data, dest_hash = packet
            return sa1_lxmf.carried(dest_hash, data, content) if args.lxmf else data == content

        def incoming(out, content):
            return sa1_lxmf.packed(out, destination, content) if args.lxmf else content

        def delivered(event, content):
            # Zdarzenie "packet" stacji: przy --lxmf koperta od celu "wici.sa1" komputera z kartą.
            expected = sa1_lxmf.envelope(computer_sa1, station_address, content) if args.lxmf else content
            return event["data"] == expected.hex()

        if args.lxmf:
            # Komputer stanowiska to odbiorca z karty stacji (stacja przyjmuje wiadomości tylko od niego).
            station.command(f"receiver {computer_sa1.hex()} {identity.get_public_key().hex()}")
            checks["station_card_receiver"] = station.wait("receiver", 5) is not None

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

        # 1. Kontrola przepływu włączona przez komputer (polecenie KISS 0x0F z wartością 1).
        checks["computer_flow_control"] = wait_for(lambda: node.status().get("usb_flow") is True, 10)

        # 2. Ogłoszenie komputera (adres OSP) przez węzeł i P1 do stacji; cel chroniony w tablicach węzła.
        destination.announce(app_data=b"OSP")
        t0 = time.time()
        e = station.wait("announce", 120, lambda e: e["dest"] == destination.hash.hex())
        checks["computer_announce_at_station"] = e is not None
        if e:
            results["computer_announce_to_station_s"] = round(time.time() - t0, 2)
        node.command(f"pinned {destination.hash.hex()}")
        pinned = node.wait("pinned", 5) or {}
        node.command(f"pinned {station_address.hex()}")
        other = node.wait("pinned", 5) or {}
        checks["computer_destination_pinned"] = pinned.get("pinned") is True and other.get("pinned") is False

        # 3. Ogłoszenie stacji przez węzeł do komputera.
        station.command("announce 57494349")
        checks["station_announce_at_computer"] = wait_for(lambda: any(a[1] == station_address for a in seen["announces"]), 120)
        station_identity = next((a[2] for a in seen["announces"] if a[1] == station_address), None)

        # 4. Pakiet okazjonalny stacja -> komputer z potwierdzeniem transportowym.
        payload = b'["WICI",1,"osp node","station to computer"]'
        target = computer_sa1 if args.lxmf else destination.hash
        station.command(f"send {target.hex()} {outgoing(payload).hex()} 120")
        sent = station.wait("sent", 10)
        handle = sent["handle"] if sent else 0
        checks["station_to_computer_packet"] = handle > 0 and wait_for(lambda: any(carried(p, payload) for p in seen["packets"]), 120)
        receipt = station.wait("receipt", 180, lambda e: e["handle"] == handle) if handle else None
        checks["station_receipt_delivered"] = bool(receipt and receipt["delivered"])

        # 5. Pakiet okazjonalny komputer -> stacja z potwierdzeniem transportowym.
        if station_identity is not None:
            out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            back = b'["WICI",1,"osp node","computer to station"]'
            r = RNS.Packet(out, incoming(out, back)).send()
            if r:
                # Limit z samej konfiguracji (bitrate interfejsu), bez set_timeout: warunek D19 dla T3.
                results["computer_receipt_timeout_s"] = round(r.timeout, 2)
            checks["computer_to_station_packet"] = station.wait("packet", 120, lambda e: delivered(e, back)) is not None
            t0 = time.time()
            checks["computer_receipt_delivered"] = bool(r) and wait_for(lambda: r.status == RNS.PacketReceipt.DELIVERED, 240)
            if checks["computer_receipt_delivered"]:
                results["computer_receipt_s"] = round(time.time() - t0, 2)

            # 6. Seria pakietów z komputera: gotowość po każdym przyjętym pakiecie, bez czekania 5 s
            # na zwolnienie blokady w Pythonie i bez odrzutów w węźle; wszystkie docierają do stacji.
            before = node.status()
            burst = [b'["WICI",1,"osp node","burst %d"]' % i for i in range(BURST)]
            t0 = time.time()
            for data in burst:
                RNS.Packet(out, incoming(out, data)).send()
            flowed = wait_for(lambda: not kiss.packet_queue and kiss.interface_ready, 30)
            results["burst_queue_empty_s"] = round(time.time() - t0, 2)
            got = set()
            end = time.time() + 300
            while len(got) < BURST and time.time() < end:
                e = station.wait("packet", max(0.1, end - time.time()))
                for data in burst:
                    if e and delivered(e, data):
                        got.add(data)
            after = node.status()
            results["burst"] = {"sent": BURST, "received": len(got), "usb_rns_in": after.get("usb_rns_in", 0) - before.get("usb_rns_in", 0),
                                "usb_ready": after.get("usb_ready", 0) - before.get("usb_ready", 0),
                                "usb_rx_drop": after.get("usb_rx_drop"), "seconds": round(time.time() - t0, 2)}
            checks["burst_without_flow_timeout"] = flowed and results["burst_queue_empty_s"] < 4
            checks["burst_delivered_without_drops"] = len(got) == BURST and after.get("usb_rx_drop") == 0
        else:
            for name in ("computer_to_station_packet", "computer_receipt_delivered", "burst_without_flow_timeout",
                         "burst_delivered_without_drops"):
                checks[name] = False
        if args.lxmf:
            flood(node, station, kiss, results, checks, lambda content: (outgoing(content), computer_sa1),
                  lambda content: wait_for(lambda: any(carried(p, content) for p in seen["packets"]), 120))
        results["node_status"] = node.status()
        if args.lxmf:
            # Cel komputera chroniony także po restarcie węzła: z tras przez USB w tablicy w FRAM.
            node.stop()
            node = Program(args.program, node_fram, node_port, station_port, args.debt, node=True)
            node.command(f"pinned {destination.hash.hex()}")
            checks["computer_destination_pinned_after_restart"] = (node.wait("pinned", 5) or {}).get("pinned") is True
    finally:
        # Koniec programu węzła zamyka pty: w Linuksie interfejs KISS dostaje EIO i przy panic_on_interface_error
        # Reticulum kończy proces (os._exit) przed wypisaniem wyniku. Panika obejmuje tylko samą próbę.
        RNS.Reticulum.panic_on_interface_error = False
        node.stop()
        station.stop()

    results["passed"] = all(checks.values())
    print(json.dumps(results, indent=2, default=str))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
