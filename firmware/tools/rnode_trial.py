# SPDX-License-Identifier: MIT
"""Hardware step 4, point 2 (firmware/README.md, "Krok 4: interfejs LoRa z radiem RNode"): 100 datagrams of 508 B
in each direction between the station and an RNode radio, with the station counters before and after.

Roles (one per laptop and direction):
  rnode-announce   Reticulum with an RNodeInterface on a real RNode (RAK4631) announces N new destinations with 325 B
                   of app data: packet 492 B + IFAC 16 B = 508 B on air (two frames, a third header-only frame).
  usb-announce     Reticulum with a KISSInterface on the USB data port of the station (station as the node of the
                   receiving station, stos.py config: flow control, bitrate 41) announces N destinations with 309 B of
                   app data; the station rebroadcasts each with its transport id (+16 B), so 492 B + IFAC 16 B = 508 B.
  rnode-listen     Reticulum with an RNodeInterface counts the marked announces (from the station or from another
                   rnode-announce) and reports sequence numbers, missing ones and arrival times.
  station-counters INFO, P1 and RNS from the diagnostic console of the station; with --before the step 4 criteria from
                   the deltas.

With --station-diag the announce roles read INFO, P1 and RNS from the diagnostic console (first CDC port) before and
after, keep the console open in between (loratx lines) and print the criteria of point 2 from the deltas. Every
announce carries a marker, a run id and a sequence number, so the receiving side can count. The result goes to a
JSON file (--out) for the Issue report (label "próba").

Run with a Python that has Reticulum at the pinned commit (e40191b) and pyserial, as rns_interop.py, e.g.:
  .venv-rns/bin/python firmware/tools/rnode_trial.py rnode-announce --port /dev/ttyACM0 --key-file key.txt \\
      --station-diag /dev/ttyACM1
On the computer tests/test_rns_stack_lora.py runs the roles against tools/rnode_emulator.py and the host program
(--port takes a pseudo-terminal as well); that proves the tool, not the radio.
"""

import argparse
import json
import math
import os
from pathlib import Path
import queue
import re
import statistics
import sys
import tempfile
import threading
import time

import rnode_framing   # tools/rnode_framing.py: MTU RNode i sekcja RNodeInterface

ROOT = Path(__file__).resolve().parents[2]
APP_NAME, ASPECT = "wici", "krok4"   # osobny cel próby: słuchacz liczy tylko swoje ogłoszenia
MARKER = b"WICI-K4/"                 # początek danych aplikacji: znacznik, potem id przebiegu (4 B) i numer (4 B)
IFAC_BYTES = rnode_framing.IFAC_BITS // 8
TRANSPORT_ID = 16                    # identyfikator transportu dodany przez stację przy retransmisji (nagłówek 2)
ANNOUNCE_BASE = 167                  # ogłoszenie bez danych aplikacji: nagłówek 19 B, klucz 64, nazwa 10, losowe 10, podpis 64
RNODE_PACKET = rnode_framing.MTU - IFAC_BYTES                 # 492 B: z IFAC 508 B w eterze
RNODE_APP_DATA = RNODE_PACKET - ANNOUNCE_BASE                 # 325 B (jak krok B rns_interop.py)
USB_PACKET = RNODE_PACKET - TRANSPORT_ID                      # 476 B od komputera; po retransmisji 492 B
USB_APP_DATA = USB_PACKET - ANNOUNCE_BASE                     # 309 B

# Tempo z RNode: samo RNode nie ma długu ciszy, więc tempo wyznacza strona stacji. Datagram 508 B zajmuje
# eter ok. 0,84 s; stacja weryfikuje podpis ogłoszenia z łącza LoRa za żeton z wiadra (żeton co 1 s, najwyżej 3
# naraz, verifyBuckets w rns_node_core.cpp) i zapisuje trasę w FRAM; własna retransmisja stacji trzyma radio
# do ok. 0,9 s. 3 s daje zapas na wszystko naraz: 100 ogłoszeń w 5 min, bez ann_limited.
RNODE_INTERVAL_S = 3.0
# Tempo przez USB: stacja wypuszcza ogłoszenia do eteru w limicie 2% czasu (ANNOUNCE_CAP_PERCENT w p1iface.h),
# czyli po 508 B (rezerwacja ok. 0,84 s) najwyżej jedno na ok. 42 s; nadmiar czeka na liście 4 ogłoszeń
# (HELD_ANNOUNCES, ann_held), a ponad nią przepada (ann_drop). Stacja nadaje każde ogłoszenie dwa razy (ponowienie
# PATHFINDER_R, bo słuchacz bez transportu go nie powtarza), więc jedno ogłoszenie z komputera kosztuje ok. 84 s
# limitu. 90 s nadąża: 100 ogłoszeń w ok. 2,5 h.
USB_INTERVAL_S = 90.0


def log(text):
    print(f"[rnode-trial] {text}", flush=True)


def app_data(run, seq, size):
    """Dane aplikacji ogłoszenia próby: znacznik, id przebiegu, numer, wypełnienie do rozmiaru."""
    head = MARKER + run + seq.to_bytes(4, "big")
    return head + bytes(i % 251 for i in range(size - len(head)))


def parse_app_data(data):
    """(id przebiegu hex, numer) z danych aplikacji próby albo None."""
    if not data or len(data) < len(MARKER) + 8 or not data.startswith(MARKER):
        return None
    n = len(MARKER)
    return data[n:n + 4].hex(), int.from_bytes(data[n + 4:n + 8], "big")


def network_key(args):
    key = args.passphrase
    if args.key_file:
        key = Path(args.key_file).read_text(encoding="utf-8").strip()
    if not key or not re.fullmatch(r"[0-9a-fA-F]{32}", key):
        raise SystemExit("network key: 32 hex digits (--passphrase or --key-file)")
    return key.lower()


def start_reticulum(interface):
    """Reticulum w katalogu tymczasowym z jednym interfejsem (sekcja [[...]] albo cała konfiguracja stos.py)."""
    import RNS  # Reticulum e40191b
    work = Path(tempfile.mkdtemp(prefix="wici_rnode_trial_"))
    (work / "rns").mkdir()
    config = interface if interface.lstrip().startswith(("#", "[reticulum]")) else f"""
[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = Yes

[logging]
  loglevel = 2

[interfaces]
{interface}"""
    (work / "rns" / "config").write_text(config, encoding="utf-8")
    # Dziennik Reticulum na stderr: na stdout podsumowanie dla operatora.
    RNS.Reticulum(str(work / "rns"), logdest=lambda line: print(line, file=sys.stderr, flush=True))
    end = time.time() + 10
    while not any(i.online for i in RNS.Transport.interfaces) and time.time() < end:
        time.sleep(0.2)
    if not any(i.online for i in RNS.Transport.interfaces):
        raise SystemExit("interface not online: check --port (Reticulum log on stderr)")
    time.sleep(1)   # RNodeInterface ustawia radio, KISS włącza kontrolę przepływu
    return RNS


# --- konsola diagnostyczna stacji -------------------------------------------------------------------------------

def is_info(m):
    return "contract" in m


def p1_part(m):
    """Część wiersza P1: {"lora": {...}} (w profilu P1 klucz "p1"); None, gdy to nie odpowiedź P1."""
    return next((v for v in m.values() if isinstance(v, dict) and "rx_datagrams" in v), None) if len(m) == 1 else None


def is_rns(m):
    return "rns" in m and "paths" in m


class DiagConsole:
    """Konsola diagnostyczna stacji (pierwszy port CDC, 115200): wiersz polecenia, odpowiedź jednym wierszem JSON.
    Port zostaje otwarty przez całą próbę, bo wiersze loratx idą tylko do czytanego portu (diagLine w measure.cpp
    pomija wiersz przy pełnym buforze). board_selftest.py otwiera port na jedną serię poleceń; tu potrzeba ciągłego
    odczytu, stąd osobna klasa."""

    def __init__(self, port):
        import serial  # pyserial
        self.link = serial.Serial(port, 115200, timeout=0.2)
        self.lines = []            # (czas, wiersz) wszystkich wierszy
        self.replies = queue.Queue()
        self.running = True
        threading.Thread(target=self._read, daemon=True).start()
        time.sleep(2)   # obraz po otwarciu portu wysyła INFO, RADIO, FRAM i JOURNAL (jak w board_selftest.py)

    def _read(self):
        while self.running:
            try:
                raw = self.link.readline()
            except Exception:
                break
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            self.lines.append((time.time(), line))
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                self.replies.put(message)

    def query(self, command, match, timeout=5):
        while not self.replies.empty():
            self.replies.get_nowait()
        self.link.write(f"{command}\n".encode())
        end = time.time() + timeout
        while time.time() < end:
            try:
                message = self.replies.get(timeout=max(0.05, end - time.time()))
            except queue.Empty:
                break
            if match(message):
                return message
        return None

    def snapshot(self):
        p1 = self.query("P1", p1_part)
        return {"time": time.time(), "INFO": self.query("INFO", is_info), "P1": p1_part(p1) if p1 else None,
                "RNS": self.query("RNS", is_rns)}

    def loratx(self, since):
        """Wiersze loratx od czasu since: (czas, wiersz JSON)."""
        out = []
        for t, line in self.lines:
            if t >= since and line.startswith('{"loratx"'):
                try:
                    out.append({"time": round(t, 3), **json.loads(line)})
                except ValueError:
                    pass
        return out

    def close(self):
        self.running = False
        self.link.close()


# --- kryteria punktu 2 ----------------------------------------------------------------------------------------

def criteria(direction, count, before, after, loratx=None):
    """Kryteria punktu 2 kroku 4 z przyrostów liczników (README firmware). Wpis: wartość, oczekiwanie, pass
    (True/False; None, gdy pola brak w obu migawkach: wtedy nie ma zaliczenia). direction: "rnode" (RNode -> stacja)
    albo "usb" (stacja -> RNode)."""
    need = math.ceil(0.99 * count)
    out = {}

    def value(part, key, snap):
        section = (snap or {}).get(part) or {}
        return section.get(key)

    def delta(part, key):
        a, b = value(part, key, before), value(part, key, after)
        return b - a if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None

    def check(name, val, expect, ok):
        out[name] = {"value": val, "expect": expect, "pass": None if val is None else bool(ok(val))}

    def record(name, val):
        out[name] = {"value": val, "expect": "recorded", "pass": None if val is None else True}

    if direction == "rnode":
        rx = delta("P1", "rx_datagrams")
        check("rx_datagrams_delta", rx, f">= {need} of {count}", lambda v: v >= need)
        header = delta("P1", "header_only")
        out["header_only_delta"] = {"value": header, "expect": "= rx_datagrams_delta (third RNode frame, one per datagram)",
                                    "pass": None if header is None or rx is None else header == rx}
        for key in ("rx_late", "rx_ring_overflow", "assembly_timeout", "split_lost"):
            check(f"{key}_delta", delta("P1", key), "0", lambda v: v == 0)
        check("ifac_invalid_delta", delta("RNS", "ifac_invalid"), "0", lambda v: v == 0)
        if value("RNS", "ann_limited", after) is not None:   # tylko rdzeń: ogłoszenia bez żetonu weryfikacji
            check("ann_limited_delta", delta("RNS", "ann_limited"), "0 (else the interval is too short)", lambda v: v == 0)
    else:
        tx = delta("P1", "tx_datagrams")
        check("tx_datagrams_delta", tx, f">= {need} of {count}", lambda v: v >= need)
        if loratx is not None:
            big = [x for x in loratx if x.get("loratx") == "sent" and x.get("len") == rnode_framing.MTU and x.get("frames") == 2]
            check("loratx_508_two_frames", len(big), f">= {need} lines \"len\":508,\"frames\":2", lambda v: v >= need)
            gaps = [round(b["time"] - a["time"], 1) for a, b in zip(big, big[1:])]
            record("loratx_gap_s_min", min(gaps) if gaps else None)
            waits = [x["tx_wait_ms"] for x in big if "tx_wait_ms" in x]
            record("loratx_tx_wait_ms_max", max(waits) if waits else None)   # dług po nadaniu: około 10 s po 508 B
        check("ann_drop_delta", delta("RNS", "ann_drop"), "0", lambda v: v == 0)
        record("ann_held_delta", delta("RNS", "ann_held"))
        check("too_large_delta", delta("RNS", "too_large"), "0", lambda v: v == 0)
    # Obie strony: praca pętli i odbioru, nadzór (punkt 4), pamięć (próby rdzenia, punkt 2).
    for key in ("loop_max_ms", "rx_service_max_ms"):
        record(key, value("INFO", key, after))
    check("rx_stalled", value("INFO", "rx_stalled", after), "false", lambda v: v is False)
    for key in ("lock_timeouts", "lock_misses", "rx_mode_lost"):
        check(f"{key}_delta", delta("INFO", key), "0", lambda v: v == 0)
    for key in ("rx_stack_free", "heap_size", "heap_free", "heap_min"):
        record(key, value("RNS", key, after))
    size, low = value("RNS", "heap_size", after), value("RNS", "heap_min", after)
    if isinstance(size, int) and size > 0 and isinstance(low, int):
        check("heap_min_30_percent", low, f">= {math.ceil(0.3 * size)} (30% of heap_size)", lambda v: v >= 0.3 * size)
    return out


def verdict(table):
    """passed: każde sprawdzenie zaliczone; incomplete: któregoś pola brak (bez zaliczenia)."""
    checks = [c for c in table.values() if c["expect"] != "recorded"]
    if any(c["pass"] is False for c in checks):
        return "failed"
    return "incomplete" if any(c["pass"] is None for c in checks) else "passed"


def print_criteria(table):
    for name, c in table.items():
        mark = {True: "ok", False: "FAIL", None: "MISSING"}[c["pass"]] if c["expect"] != "recorded" else "  "
        print(f"  {mark:7s} {name:24s} {c['value']!s:>10s}   expect {c['expect']}")
    print(f"  criteria: {verdict(table)}")


# --- role --------------------------------------------------------------------------------------------------------

def announce_role(args, result):
    rnode = args.role == "rnode-announce"
    if rnode:
        interface = rnode_framing.rnode_interface(args.port, network_key(args), args.txpower)
        size, packet_bytes = RNODE_APP_DATA, RNODE_PACKET
    else:
        # Komputer stanowiska jak aplikacja stanowiska: konfiguracja z stos.py (KISS, kontrola przepływu, bitrate 41).
        sys.path.insert(0, str(ROOT / "software" / "laptop"))
        from wici.stanowisko import stos
        interface = stos.config(args.port, stos.BITRATE)
        result["bitrate"] = stos.BITRATE
        size, packet_bytes = USB_APP_DATA, USB_PACKET
    console = DiagConsole(args.station_diag) if args.station_diag else None
    try:
        if console:
            result["station_before"] = console.snapshot()
        RNS = start_reticulum(interface)
        run = os.urandom(4)
        result.update(run=run.hex(), app_data_bytes=size, packet_bytes=packet_bytes,
                      on_air_bytes=packet_bytes + IFAC_BYTES + (0 if rnode else TRANSPORT_ID), sent=[])
        t0 = time.monotonic()
        started = time.time()
        for seq in range(args.count):
            delay = t0 + seq * args.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            destination = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, ASPECT)
            packet = destination.announce(app_data=app_data(run, seq, size), send=False)
            packet.pack()
            # Rozmiar z gotowego pakietu (jak krok B rns_interop.py): z IFAC i ew. identyfikatorem transportu 508 B.
            if len(packet.raw) != packet_bytes:
                raise SystemExit(f"announce of {len(packet.raw)} B, expected {packet_bytes} B")
            packet.send()
            result["sent"].append({"seq": seq, "dest": destination.hash.hex(), "time": round(time.time(), 3)})
            log(f"sent {seq + 1}/{args.count} {destination.hash.hex()}")
        result["send_s"] = round(time.time() - started, 1)
        settle(args, console, rnode)
        if console:
            result["station_after"] = console.snapshot()
            result["loratx"] = console.loratx(started)
            result["criteria"] = criteria("rnode" if rnode else "usb", args.count, result["station_before"],
                                          result["station_after"], result["loratx"])
    finally:
        if console:
            result["console_lines"] = [line for _, line in console.lines]
            console.close()
    log(f"{args.count} announces of {packet_bytes} B ({size} B app data, {result['on_air_bytes']} B on air) "
        f"in {result['send_s']} s, run {result['run']}")


def settle(args, console, rnode):
    """Po ostatnim ogłoszeniu: z RNode czas na nadanie i odbiór; przez USB do opróżnienia kolejki stacji (q_held, q_len
    w RNS) albo do --timeout. Bez konsoli stacji tylko krótka chwila, żeby interfejs oddał ostatni pakiet."""
    timeout = args.timeout if args.timeout is not None else (15 if rnode else 600)
    if not console:
        time.sleep(min(timeout, 15 if rnode else 5))
        return
    end = time.time() + timeout
    time.sleep(min(timeout, 10))
    while not rnode and time.time() < end:
        rns = console.query("RNS", is_rns) or {}
        if rns.get("q_held") == 0 and rns.get("q_len") == 0 and rns.get("wait_ms", 0) == 0:
            break
        time.sleep(5)


def listen_role(args, result):
    RNS = start_reticulum(rnode_framing.rnode_interface(args.port, network_key(args), args.txpower))
    heard = []
    done = threading.Event()

    class Announces:
        aspect_filter = f"{APP_NAME}.{ASPECT}"

        def received_announce(self, destination_hash, announced_identity, app_data):
            data = app_data
            parsed = parse_app_data(data)
            if not parsed:
                return
            run, seq = parsed
            heard.append({"run": run, "seq": seq, "dest": destination_hash.hex(), "app_data_bytes": len(data),
                          "hops": RNS.Transport.hops_to(destination_hash), "time": round(time.time(), 3)})
            log(f"heard run {run} seq {seq} ({len(data)} B app data)")
            if len({h["seq"] for h in heard if h["run"] == run}) >= args.count:
                done.set()

    RNS.Transport.register_announce_handler(Announces())
    log(f"listening on {args.port} for up to {args.timeout} s (Ctrl+C ends and writes the report)")
    try:
        done.wait(args.timeout)
    except KeyboardInterrupt:
        pass
    runs = {}
    for h in heard:
        runs.setdefault(h["run"], []).append(h)
    result["heard"] = heard
    result["runs"] = {}
    for run, items in runs.items():
        seqs = sorted({h["seq"] for h in items})
        times = [h["time"] for h in items]
        gaps = [round(b - a, 2) for a, b in zip(times, times[1:])]
        summary = {"count": len(items), "unique": len(seqs), "missing": sorted(set(range(args.count)) - set(seqs)),
                   "duplicates": len(items) - len(seqs), "app_data_bytes": sorted({h["app_data_bytes"] for h in items}),
                   "hops": sorted({h["hops"] for h in items}), "first": times[0], "last": times[-1],
                   "gap_s": {"min": min(gaps), "median": statistics.median(gaps), "max": max(gaps)} if gaps else None,
                   "passed": len(seqs) >= math.ceil(0.99 * args.count)}
        result["runs"][run] = summary
        print(f"run {run}: {summary['unique']}/{args.count} unique ({summary['duplicates']} duplicates), "
              f"app data {summary['app_data_bytes']} B, hops {summary['hops']}, gaps {summary['gap_s']}, "
              f"missing {summary['missing'][:20]}{' ...' if len(summary['missing']) > 20 else ''}: "
              f"{'ok' if summary['passed'] else 'FAIL'} (>= {math.ceil(0.99 * args.count)})")
    if not runs:
        print("no marked announce heard")


def counters_role(args, result):
    console = DiagConsole(args.station_diag)
    try:
        result["station"] = console.snapshot()
    finally:
        result["console_lines"] = [line for _, line in console.lines]
        console.close()
    if args.before:
        # Wcześniejszy plik tego narzędzia: migawka station-counters albo "po" roli z --station-diag.
        earlier = json.loads(Path(args.before).read_text(encoding="utf-8"))
        before = earlier.get("station") or earlier.get("station_after")
        result["criteria"] = criteria(args.direction, args.count, before, result["station"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n".join(__doc__.splitlines()[2:]))
    roles = parser.add_subparsers(dest="role", required=True)

    def common(p, port_help, interval=None):
        p.add_argument("--port", required=port_help is not None, help=port_help)
        p.add_argument("--count", type=int, default=100, help="announces to send or expect (default 100)")
        if interval is not None:
            p.add_argument("--interval", type=float, default=interval, help=f"seconds between announces (default {interval:g})")
        p.add_argument("--out", help="JSON results file (default rnode-trial-<role>-<time>.json in the current folder)")

    def radio(p):
        p.add_argument("--passphrase", help="network key of the station (32 hex digits), the IFAC passphrase")
        p.add_argument("--key-file", help="file with the network key instead of --passphrase")
        p.add_argument("--txpower", type=int, default=13, help="RNode TX power in dBm (default 13, the pilot profile)")

    def diag(p):
        p.add_argument("--station-diag", help="diagnostic serial port of the station: INFO, P1, RNS before and after")

    p = roles.add_parser("rnode-announce", help="announce N destinations of 508 B on air through an RNode")
    common(p, "serial port of the RNode (or a pseudo-terminal of tools/rnode_emulator.py)", RNODE_INTERVAL_S)
    radio(p)
    diag(p)
    p.add_argument("--timeout", type=float, help="seconds to wait after the last announce before the counters (default 15)")
    p = roles.add_parser("usb-announce", help="announce N destinations through the station USB data port (no IFAC on USB)")
    common(p, "USB data port of the station (second CDC port) or the pseudo-terminal of the host program", USB_INTERVAL_S)
    diag(p)
    p.add_argument("--timeout", type=float, help="with --station-diag: at most this many seconds after the last announce for "
                                                 "the station queue to drain (default 600)")
    p = roles.add_parser("rnode-listen", help="count the marked announces heard through an RNode")
    common(p, "serial port of the RNode (or a pseudo-terminal of tools/rnode_emulator.py)")
    radio(p)
    p.add_argument("--timeout", type=float, default=7200, help="seconds to listen; ends earlier when --count are heard (default 7200)")
    p = roles.add_parser("station-counters", help="INFO, P1 and RNS of the station; with --before the criteria")
    p.add_argument("--station-diag", required=True, help="diagnostic serial port of the station")
    p.add_argument("--before", help="earlier JSON file of this tool: criteria from the deltas")
    p.add_argument("--direction", choices=("rnode", "usb"), default="rnode", help="criteria of which direction (default rnode)")
    p.add_argument("--count", type=int, default=100, help="announces sent in the trial (default 100)")
    p.add_argument("--out", help="JSON results file (default rnode-trial-<role>-<time>.json in the current folder)")
    args = parser.parse_args(argv)
    if args.role in ("rnode-announce", "rnode-listen"):
        network_key(args)   # błąd klucza przed otwarciem portów

    result = {"tool": "rnode_trial.py", "role": args.role, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "reticulum": "e40191b",
              "args": {k: v for k, v in vars(args).items() if k not in ("passphrase",)}}
    {"rnode-announce": announce_role, "usb-announce": announce_role, "rnode-listen": listen_role,
     "station-counters": counters_role}[args.role](args, result)
    if "criteria" in result:
        print("station counters (step 4, point 2):")
        print_criteria(result["criteria"])
        result["verdict"] = verdict(result["criteria"])
    out = Path(args.out or f"rnode-trial-{args.role}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"saved {out}")
    failed = result.get("verdict") == "failed" or any(not r["passed"] for r in result.get("runs", {}).values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
