# SPDX-License-Identifier: MIT
"""Compatibility trial of the OSP node (decision D19) with reference Reticulum (Python), without a radio.

Two station programs (the "host" PlatformIO program, firmware/src/host/node_host.cpp) are joined by the
emulated P1 link over UDP: a station and a station in the OSP node configuration (--osp-node). The node
has the second Reticulum interface over USB; here the USB data port is a pseudo-terminal, and this
process runs reference Reticulum with a KISSInterface (flow control on) on it, as the computer of the
receiving station does (docs/spec/stanowisko-osp.md, "Komputer i aplikacja OSP"; radio.md, "Interfejs
Reticulum przez USB"). The computer has transport and network interfaces off; the node forwards.

Checks: the node has no address of its own and does not announce; the computer turns flow control on;
the computer announce reaches the station through the node over P1, and its destination is protected
in the node tables; the station announce reaches the computer; an opportunistic packet in both
directions with a transport proof, the computer receipt time-out set only by the interface bitrate
in the Reticulum config (no set_timeout, no change in the stack code); a burst of packets from the computer passes the KISS flow control
without the 5 s time-out of the Python interface and without drops at the node.

Run with a Python that has Reticulum at the pinned commit (e40191b) and pyserial, for example:
  .venv-rns/bin/python firmware/tools/rns_osp_node.py --program firmware/.pio/build/host/program
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


def log(text):
    print(f"[osp-node] {text}", file=sys.stderr, flush=True)


class Program:
    """The host program with line JSON events."""

    def __init__(self, program, fram, listen, peer, debt, osp_node=False):
        extra = ["--osp-node"] if osp_node else []
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--debt", type=int, default=12, help="silence debt factor of the emulated P1 link")
    parser.add_argument("--port", type=int, default=47440)
    parser.add_argument("--bitrate", type=int, default=24,
                        help="bitrate of the computer KISS interface in the Reticulum config (bit/s); it sets the receipt "
                             "timeouts: 500 B x 8 / bitrate + 6 s + 6 s per hop")
    args = parser.parse_args()

    import RNS  # noqa: E402 (needs the reference Reticulum)

    work = tempfile.mkdtemp(prefix="wici_osp_node_")
    station_port, node_port = args.port, args.port + 1
    results = {"reticulum": "e40191b", "debt_factor": args.debt, "bitrate": args.bitrate, "checks": {}}
    checks = results["checks"]
    node = Program(args.program, os.path.join(work, "node.bin"), node_port, station_port, args.debt, osp_node=True)
    station = Program(args.program, os.path.join(work, "station.bin"), station_port, node_port, args.debt)
    try:
        if not node.ready or not station.ready:
            raise RuntimeError("host programs did not start")
        pty = node.ready["usb"]
        station_address = bytes.fromhex(station.ready["address"])
        checks["node_without_address"] = node.ready["osp_node"] is True and node.ready["address"] == "0" * 32
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
        RNS.Reticulum(os.path.join(work, "rns"))
        kiss = next(i for i in RNS.Transport.interfaces if type(i).__name__ == "KISSInterface")

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
        station.command(f"send {destination.hash.hex()} {payload.hex()} 120")
        sent = station.wait("sent", 10)
        handle = sent["handle"] if sent else 0
        checks["station_to_computer_packet"] = handle > 0 and wait_for(lambda: any(p[1] == payload for p in seen["packets"]), 120)
        receipt = station.wait("receipt", 180, lambda e: e["handle"] == handle) if handle else None
        checks["station_receipt_delivered"] = bool(receipt and receipt["delivered"])

        # 5. Pakiet okazjonalny komputer -> stacja z potwierdzeniem transportowym.
        if station_identity is not None:
            out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            back = b'["WICI",1,"osp node","computer to station"]'
            r = RNS.Packet(out, back).send()
            if r:
                # Limit z samej konfiguracji (bitrate interfejsu), bez set_timeout: warunek D19 dla T3.
                results["computer_receipt_timeout_s"] = round(r.timeout, 2)
            checks["computer_to_station_packet"] = station.wait("packet", 120, lambda e: e["data"] == back.hex()) is not None
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
                RNS.Packet(out, data).send()
            flowed = wait_for(lambda: not kiss.packet_queue and kiss.interface_ready, 30)
            results["burst_queue_empty_s"] = round(time.time() - t0, 2)
            got = set()
            end = time.time() + 300
            while len(got) < BURST and time.time() < end:
                e = station.wait("packet", max(0.1, end - time.time()))
                if e and bytes.fromhex(e["data"]) in burst:
                    got.add(e["data"])
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
        results["node_status"] = node.status()
    finally:
        node.stop()
        station.stop()

    results["passed"] = all(checks.values())
    print(json.dumps(results, indent=2, default=str))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
