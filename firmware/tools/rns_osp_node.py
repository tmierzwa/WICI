# SPDX-License-Identifier: MIT
"""Compatibility trial of the OSP node (decision D19) with reference Reticulum (Python), without a radio.

Two station programs (the "host-port" PlatformIO program, firmware/src/host/node_host.cpp) are joined by the
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

With --lxmf (both programs on the station Reticulum core, "host" since stage R6-3, stage R4b) the station destination
is "lxmf.delivery", the computer is the card receiver of the station, and the packets carry SA1 as LXMF
messages (tools/sa1_lxmf.py), as from a plain LXMF client on the computer. More checks on the core:
packets from the computer go on P1 in class K1; a flood from the computer side (announces with a bad
signature and KISS garbage, written past the Python interface) during a report from the station: at most
one asymmetric operation in a node loop pass, P1 receive steps still run (interleaved with USB), no new
computer destination, and the report is delivered with its receipt; a flood of cheap packets (unknown
destinations) that keeps the KISS buffer full does not stop the rebroadcast of a station announce to the
computer; a packet with the IFAC flag from USB is dropped; a route of the computer destination moved to
P1 removes its protection; a ninth computer destination evicts the oldest, also after a restart of the
node (rebuilt from the routes through USB with 1 hop in FRAM).

With --link lora (with --lxmf, host and host-port) the programs use the emulated LoRa link (node_host --link lora): on-air
frames of the RNode header, one per UDP datagram, through a small shared medium (class Air) that joins the programs as
neighbours; there is no RNode emulator here, the computer is behind USB. The bitrate of the KISS interface is 41 b/s
(radio.md, "Kryterium bitrate"). Checks added to the steps above (the flood steps of the P1 run are left out): a packet of 493-500 B from USB is dropped before the
radio and counted (too_large); a LoRa frame pair without IFAC does not reach the computer; LXMRouter in Python on the
computer sends an LXMF SA1 message to the station and gets the delivery proof before any retry (delivery_attempts 1,
the proof earlier than next_delivery_attempt), with 3 attempts and an interval of 2 x (500 x 8 / bitrate - ...) set by the
bitrate alone (D19); RECEIVED- and STATUS-like SA1 messages from a station reach the computer over one hop and over two
hops (station - relay - node, three host programs); 50 LXMF messages of the BULLETIN size to one station, sent as the
station application sends them (at most 4 in flight, the next after DELIVERED or FAILED), all delivered with no drop in the
USB buffer of the node (stanowisko-osp.md, "Wysyłka"); with the computer disconnected the node still forwards the announces
of two stations that do not hear each other. The host program has no station application layer: RECEIVED and STATUS
are SA1 contents sent with the "send" command, not messages made by station.cpp.

Run with a Python that has Reticulum at the pinned commit (e40191b) and pyserial, for example:
  .venv-rns/bin/python firmware/tools/rns_osp_node.py --program firmware/.pio/build/host-port/program
Prints one JSON object with the results; exit code 0 when every check passed.
"""

import argparse
import json
import os
import queue
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME = "wici"
ASPECT = "sa1"
NETWORK_KEY = "5749434954335f696661635f74657374"  # 16 B test key, not a field key
BURST = 6
BULLETIN = 50             # --link lora: BULLETIN do 50 stacji, wiadomości LXMF jedna za drugą
IN_FLIGHT = 4             # najwyżej tyle wiadomości w drodze naraz (stanowisko-osp.md, "Wysyłka"; bufor USB węzła ma 8 slotów)
LORA_BITRATE = 41         # bitrate interfejsu KISS komputera w próbie LoRa (radio.md, kryterium bitrate)
FLOOD_INTERVAL_S = 0.02   # zalew z USB: ramka co 20 ms (ok. 50/s, ponad limit weryfikacji i bufor KISS)
USB_PINNED = 8            # cele komputera chronione w węźle (rns_node.h)


def kiss_frame(data, command=0x00):
    from RNS.Interfaces.KISSInterface import KISS
    return bytes([KISS.FEND, command]) + KISS.escape(data) + bytes([KISS.FEND])


def announce_raw(destination):
    """Bajty nowego ogłoszenia celu (Destination.announce bez wysłania)."""
    packet = destination.announce(send=False)
    packet.pack()
    return packet.raw


def log(text):
    print(f"[osp-node] {text}", file=sys.stderr, flush=True)


class Program:
    """The host program with line JSON events."""

    def __init__(self, program, fram, listen, peer, debt, node=False, link="p1"):
        extra = ["--node"] if node else []
        extra += ["--link", link, "--trace"] if link != "p1" else []
        self.proc = subprocess.Popen([program, "--fram", fram, "--ifac", NETWORK_KEY, "--listen", str(listen),
                                      "--peer", str(peer), "--debt", str(debt)] + extra,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.events = queue.Queue()
        self.air = []   # --link lora: zdarzenia "tx" (datagram nadany) i "rx" (ramka odebrana) ze śladu --trace
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
        return self.wait("status", 5) or {}

    def stop(self):
        try:
            self.command("quit")
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


class Air:
    """Wspólne medium łącza LoRa na komputerze: ramka (jeden datagram UDP) wysłana przez program trafia do jego sąsiadów.
    Program ma port odbioru (--listen) i port medium (--peer); sąsiedztwo dodaje i zdejmuje próba w trakcie pracy."""

    def __init__(self):
        self.listen = {}    # nazwa -> port odbioru programu
        self.sockets = {}   # gniazdo medium -> nazwa
        self.near = set()   # pary sąsiadów
        self.out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, name, listen_port):
        """Rejestruje program; zwraca port medium, który program dostaje jako --peer."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        with self.lock:
            self.listen[name] = listen_port
            self.sockets[sock] = name
        return sock.getsockname()[1]

    def link(self, a, b):
        with self.lock:
            self.near.add(frozenset((a, b)))

    def unlink(self, a, b):
        with self.lock:
            self.near.discard(frozenset((a, b)))

    def _run(self):
        while True:
            with self.lock:
                sockets = list(self.sockets)
            ready, _, _ = select.select(sockets, [], [], 0.2)
            for sock in ready:
                data = sock.recv(2048)
                with self.lock:
                    name = self.sockets[sock]
                    targets = [self.listen[other] for pair in self.near if name in pair for other in pair if other != name]
                for port in targets:
                    self.out.sendto(data, ("127.0.0.1", port))


def flood(node, station, kiss, results, checks, outgoing, received):
    """Zalew z USB (dowolny laptop podłączony w kryzysie, także zawirusowany) przy ruchu P1: ogłoszenia
    z błędnym podpisem (różne cele, więc każde idzie do weryfikacji) i śmieci KISS (ramki ponad 500 B,
    nieznane polecenia, błędne sekwencje, ramki bez końca) zapisywane w port szeregowy obok interfejsu
    Reticulum. W tym czasie zgłoszenie stacji przez węzeł do komputera z potwierdzeniem."""
    import RNS
    from RNS.Interfaces.KISSInterface import KISS

    frame = kiss_frame
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
                        "usb_rns_in": delta("usb_rns_in"), "usb_rx_drop": delta("usb_rx_drop"),
                        "usb_ann_limited": delta("usb_ann_limited"), "usb_rx_invalid": delta("usb_rx_invalid"),
                        "usb_rx_large": delta("usb_rx_large"), "usb_pinned": delta("usb_pinned"), "p1_rx_ok": delta("rx_ok"),
                        "loop_ops_max": after.get("loop_ops_max")}
    checks["flood_report_delivered"] = bool(got and receipt and receipt["delivered"])
    checks["flood_one_operation_per_loop"] = after.get("loop_ops_max") == 1
    # Kroki P1 w węźle w trakcie zalewu (zgłoszenie i dowód przez P1) i limit weryfikacji ogłoszeń z USB.
    checks["flood_p1_steps_run"] = delta("rx_ok") >= 2
    checks["flood_usb_announces_limited"] = delta("usb_ann_limited") > 0 and delta("usb_rx_invalid") > 0
    # Ogłoszenia ze złym podpisem nie dopisują celów komputera.
    checks["flood_bad_announces_not_pinned"] = delta("usb_pinned") == 0


def cheap_flood(node, station, kiss, results, checks, station_announces):
    """Zalew tanimi pakietami z USB bez wolnych obiegów węzła (pakiety do nieznanych celów, bez kryptografii,
    bufor KISS pełny przez cały czas): retransmisja ogłoszenia stacji do komputera nadal wychodzi, bo krok USB
    bez pracy asymetrycznej nie wstrzymuje poll()."""
    stop = threading.Event()
    sent = {"frames": 0}

    def run():
        while not stop.is_set():
            chunk = b"".join(kiss_frame(bytes([0x00, 0x00]) + os.urandom(16) + b"\x00" + os.urandom(24)) for _ in range(64))
            kiss.serial.write(chunk)
            sent["frames"] += 64

    before = node.status()
    count = station_announces()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(3)
    t0 = time.time()
    station.command("announce 57494349")
    end = time.time() + 90
    while station_announces() == count and time.time() < end:
        time.sleep(0.1)
    arrived = station_announces() > count
    stop.set()
    thread.join()
    after = node.status()
    results["cheap_flood"] = {"frames": sent["frames"], "seconds": round(time.time() - t0, 2),
                              "usb_rns_in": after.get("usb_rns_in", 0) - before.get("usb_rns_in", 0),
                              "usb_rx_drop": after.get("usb_rx_drop", 0) - before.get("usb_rx_drop", 0),
                              "loop_ops_max": after.get("loop_ops_max")}
    checks["cheap_flood_rebroadcast_reaches_computer"] = arrived
    checks["cheap_flood_one_operation_per_loop"] = after.get("loop_ops_max") == 1


def computer_destinations(node, kiss, destination, node_port, results, checks, wait_for):
    """Cele komputera w węźle na rdzeniu: pakiet z flagą IFAC z USB odpada; trasa celu przeniesiona na P1 zdejmuje
    ochronę (i wraca z nowym ogłoszeniem przez USB); dziewiąty cel komputera wypiera najstarszy."""
    import socket
    import RNS
    import rns_vectors

    def pinned(dest):
        node.command(f"pinned {dest.hex()}")
        return (node.wait("pinned", 5) or {}).get("pinned") is True

    # Flaga IFAC na USB (interfejs bez IFAC): ważne ogłoszenie nowego celu z ustawionym bitem 7 odpada, jak w Pythonie.
    other = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    raw = announce_raw(other)
    before = node.status()
    kiss.serial.write(kiss_frame(bytes([raw[0] | 0x80]) + raw[1:]))
    dropped = wait_for(lambda: node.status().get("usb_rx_ifac", 0) == before.get("usb_rx_ifac", 0) + 1, 10)
    checks["usb_ifac_flag_dropped"] = dropped and not pinned(other.hash) and node.status().get("usb_rx_invalid") == before.get("usb_rx_invalid")

    # Trasa celu komputera przez P1: to samo ogłoszenie (nowsze, tyle samo skoków) z kodem IFAC sieci wprost do węzła.
    wire = RNS.Transport.handle_outgoing_ifac(rns_vectors.ifac_interface(NETWORK_KEY), announce_raw(destination))
    before = node.status()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(wire, ("127.0.0.1", node_port))
    unpinned = wait_for(lambda: not pinned(destination.hash), 30)
    middle = node.status()
    # Znowu przez USB; trasa o tej samej liczbie skoków zmienia się tylko z ogłoszeniem o późniejszym czasie emisji
    # (sekundy, should_add), więc nie w tej samej sekundzie co ogłoszenie przez P1.
    time.sleep(1.1)
    destination.announce()
    repinned = wait_for(lambda: pinned(destination.hash), 30)
    keys = ("rx_ok", "ifac_invalid", "rx_invalid", "ann_limited", "rx_duplicate", "rx_ignored", "usb_rx_invalid", "usb_ann_limited")
    results["route_switch"] = {"unpinned": unpinned, "repinned": repinned,
                               **{k: middle.get(k, 0) - before.get(k, 0) for k in keys}}
    checks["route_on_p1_unpins_computer_destination"] = unpinned and repinned

    # Osiem nowych celów komputera (po ok. 1 s, w limicie weryfikacji USB): najstarszy (cel komputera) wyparty.
    # Czas użycia trasy ma rozdzielczość 1 s: pierwszy nowy cel nie w tej samej sekundzie co cel komputera.
    time.sleep(1.2)
    extra = [RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
             for _ in range(USB_PINNED)]
    for d in extra:
        d.announce()
        time.sleep(1.2)
    newest = wait_for(lambda: all(pinned(d.hash) for d in extra), 30)
    checks["ninth_destination_evicts_oldest"] = newest and not pinned(destination.hash) and node.status().get("usb_pinned") == USB_PINNED
    return extra


class Programs:
    """Dodatkowe stacje próby LoRa (stacja dwóch skoków, dwie stacje przy węźle bez komputera): każda z własnym plikiem FRAM
    na wspólnym medium Air, słyszy wskazanych sąsiadów."""

    def __init__(self, args, work, air, link):
        self.args, self.work, self.air, self.link = args, work, air, link
        self.items = []

    def add(self, name, near):
        import udp_ports
        listen = udp_ports.free_udp_ports(1)[0]
        program = Program(self.args.program, os.path.join(self.work, name + ".bin"), listen, self.air.add(name, listen),
                          self.args.debt, link=self.link)
        if not program.ready:
            raise RuntimeError(f"host program {name} did not start")
        self.items.append(program)
        for other in near:
            self.air.link(name, other)
        return program

    def stop(self):
        for program in self.items:
            program.stop()


def lora_checks(args, work, air, programs, node, station, kiss, identity, destination, station_identity, station_address,
                node_port, seen, results, checks, wait_for, sa1_lxmf):
    """Sprawdzenia łącza LoRa węzła stanowiska (radio.md, "Kryterium bitrate"; plan L7): pakiety z USB ponad
    największy pakiet łącza, ramki bez IFAC, LXMRouter w Pythonie (D19), przekaźnik i dwa skoki, węzeł bez komputera."""
    import LXMF
    import RNS
    import rnode_framing

    def inject(port, datagram):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for frame in rnode_framing.rnode_transmit(datagram, 0):
                sock.sendto(frame, ("127.0.0.1", port))

    # Pakiet z USB 493-500 B (ponad 492 B, największy pakiet LoRa bez IFAC): odrzut przed radiem, licznik too_large.
    junk = bytes([0x00, 0x00]) + os.urandom(16) + b"\x00"
    before = node.status()
    air_at = len(node.air)
    for size in (493, 500):
        kiss.serial.write(kiss_frame(junk + os.urandom(size - len(junk))))
    counted = wait_for(lambda: node.status().get("too_large", 0) == before.get("too_large", 0) + 2, 10)
    after = node.status()
    # Bez porównania tx_sent: węzeł może w tym czasie retransmitować cudze ogłoszenia. Datagram z tych pakietów
    # (bez IFAC albo z IFAC 16 B) nie pojawia się w śladzie nadawania.
    junk_on_air = any(e["event"] == "tx" and e["length"] in (493, 500, 509, 516) for e in node.air[air_at:])
    checks["usb_493_500_dropped_and_counted"] = counted and not junk_on_air and after.get("usb_rx_invalid") == before.get("usb_rx_invalid")

    # LXMRouter na komputerze: LXMF SA1 do stacji, dowód przed jakimkolwiek ponowieniem (D19).
    router = LXMF.LXMRouter(storagepath=os.path.join(work, "lxmf"))
    router_identity = RNS.Identity()
    router_destination = router.register_delivery_identity(router_identity, display_name="stanowisko")
    router_sa1 = sa1_lxmf.sa1_of(router_identity)
    received = []
    router.register_delivery_callback(lambda message: received.append(message))
    card = f"receiver {router_sa1.hex()} {router_identity.get_public_key().hex()}"
    station.command(card)
    station.wait("receiver", 5)
    router.announce(router_destination.hash)
    learned = station.wait("announce", 120, lambda e: e["dest"] == router_destination.hash.hex()) is not None
    out = RNS.Destination(station_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

    def to_station(target, receiver_events, text):
        """Wiadomość LXMF z routera do stacji (cel out); zwraca (wiadomość, czasy, czy dotarła i czy jest dowód)."""
        message = LXMF.LXMessage(target, router_destination, text, "SA1", desired_method=LXMF.LXMessage.OPPORTUNISTIC)
        t0 = time.time()
        router.handle_outbound(message)
        arrived = receiver_events.wait("packet", 400, lambda e: e["data"] == sa1_lxmf.envelope(router_sa1, bytes.fromhex(receiver_events.ready["address"]),
                                                                                              text.encode()).hex()) is not None
        proved = wait_for(lambda: message.state == LXMF.LXMessage.DELIVERED, 400)
        return message, t0, time.time(), arrived and proved

    message, t0, t_proof, ok = to_station(out, station, '[3,"osp node","LXMRouter to station"]')
    # Kryterium bitrate: limit pierwszego skoku 500 x 8 / bitrate + 6 s, odstęp prób 2 x (limit - 6 s) + 6 s.
    interval = 2 * (500 * 8 / args.bitrate) + 6
    attempt_at = message.next_delivery_attempt - interval
    results["lxmf"] = {"attempts": message.delivery_attempts, "max_attempts": message.max_delivery_attempts, "interval_s": round(interval, 1),
                       "proof_after_s": round(t_proof - t0, 1), "next_attempt_after_s": round(message.next_delivery_attempt - t0, 1)}
    checks["lxmf_router_to_station_with_proof"] = learned and ok
    checks["lxmf_no_retry_before_proof"] = message.delivery_attempts == 1 and t_proof < message.next_delivery_attempt
    checks["lxmf_three_attempts"] = message.max_delivery_attempts == 3
    checks["lxmf_interval_from_bitrate_alone"] = interval >= 201 and t0 - 1 <= attempt_at <= t_proof + 1

    # BULLETIN do 50 stacji tak, jak go rozsyła aplikacja stanowiska ("Wysyłka": po kolei, najwyżej IN_FLIGHT wiadomości
    # w drodze). Czas kanału jednego pakietu (ok. 5 s) jest dłuższy niż 5 s blokady interfejsu KISS w Pythonie, więc
    # surowa seria 50 pakietów przepełniłaby bufor USB węzła; przy 4 w drodze węzeł zawsze ma wolny slot. Do jednej stacji.
    finished = (LXMF.LXMessage.DELIVERED, LXMF.LXMessage.FAILED, LXMF.LXMessage.REJECTED, LXMF.LXMessage.CANCELLED)
    before = node.status()
    t0 = time.time()
    sent, pending = [], []
    while len(sent) < BULLETIN or pending:
        pending = [m for m in pending if m.state not in finished]
        while len(sent) < BULLETIN and len(pending) < IN_FLIGHT:
            n = len(sent) + 1   # SA1 BULLETIN [1,4,id,event,text], każda treść inna
            message = LXMF.LXMessage(out, router_destination, f'[1,4,{n},{n},"osp node bulletin {n}"]', "SA1",
                                     desired_method=LXMF.LXMessage.OPPORTUNISTIC)
            router.handle_outbound(message)
            sent.append(message)
            pending.append(message)
        if time.time() - t0 > 900:   # przed limitem 3000 s próby w tests/test_rns_stack.py
            break
        time.sleep(0.1)
    after = node.status()
    delivered_count = sum(m.state == LXMF.LXMessage.DELIVERED for m in sent)
    drops = after.get("usb_rx_drop", 0) - before.get("usb_rx_drop", 0)
    results["bulletin_paced"] = {"messages": len(sent), "delivered": delivered_count, "failed": sum(m.state == LXMF.LXMessage.FAILED for m in sent),
                                 "in_flight": IN_FLIGHT, "delivery_attempts": sum(m.delivery_attempts for m in sent),
                                 "usb_rx_drop": drops, "seconds": round(time.time() - t0, 1)}
    checks["bulletin_50_paced"] = len(sent) == BULLETIN and delivered_count == BULLETIN and drops == 0

    # Ramki LoRa bez IFAC nie dochodzą do komputera (po BULLETIN, gdy dowody poprzednich kroków już wróciły): licznik ifac_missing w węźle, pakiet nie dociera do Reticulum w Pythonie.
    before = node.status()
    packets = len(seen["packets"])
    inject(node_port, bytes([0x00, 0x00]) + destination.hash + bytes([0x00]) + b"no ifac")
    time.sleep(1.5)
    after = node.status()
    checks["lora_without_ifac_not_to_computer"] = (after.get("ifac_missing") == before.get("ifac_missing", 0) + 1
                                                   and after.get("usb_rns_out", 0) == before.get("usb_rns_out", 0) and len(seen["packets"]) == packets)

    def station_to_router(sender, text):
        """RECEIVED- i STATUS-podobna wiadomość SA1 od stacji do routera; (dotarła, dowód w stacji)."""
        content = text.encode()
        sender.command(f"send {router_sa1.hex()} {sa1_lxmf.envelope(bytes.fromhex(sender.ready['address']), router_sa1, content).hex()} 400")
        handle = (sender.wait("sent", 10) or {}).get("handle", 0)
        arrived = handle > 0 and wait_for(lambda: any(m.content == content and m.signature_validated for m in received), 400)
        receipt = sender.wait("receipt", 400, lambda e: e["handle"] == handle) if handle else None
        return arrived, bool(receipt and receipt["delivered"])

    one_hop = [station_to_router(station, f'[4,"osp node","{kind} over one hop"]') for kind in ("RECEIVED", "STATUS")]
    checks["received_status_one_hop"] = all(a and r for a, r in one_hop)

    # Dwa skoki: stacja A słyszy tylko przekaźnik (stacja z poprzednich kroków), przekaźnik słyszy węzeł.
    a = programs.add("a", near=("station",))
    a.command(card)
    a.wait("receiver", 5)
    a.command("announce 57494349")
    a_address = bytes.fromhex(a.ready["address"])
    # Ogłoszenie przez przekaźnik ma o skok więcej niż ogłoszenie stacji słyszanej przez sam węzeł.
    checks["two_hops_announce_at_computer"] = wait_for(lambda: RNS.Transport.hops_to(a_address) == RNS.Transport.hops_to(station_address) + 1, 180)
    router.announce(router_destination.hash)
    checks["two_hops_announce_at_station"] = a.wait("announce", 180, lambda e: e["dest"] == router_destination.hash.hex()) is not None
    two_hops = [station_to_router(a, f'[4,"osp node","{kind} over two hops"]') for kind in ("RECEIVED", "STATUS")]
    checks["received_status_two_hops"] = all(x and r for x, r in two_hops)
    # Komputer do stacji przez dwa skoki: dowód wraca przed ponowieniem także tu.
    out_a = RNS.Destination(RNS.Identity.recall(a_address), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
    message, t0, t_proof, ok = to_station(out_a, a, '[3,"osp node","LXMRouter to station over two hops"]')
    results["lxmf_two_hops"] = {"attempts": message.delivery_attempts, "proof_after_s": round(t_proof - t0, 1)}
    checks["lxmf_two_hops_with_proof_before_retry"] = ok and message.delivery_attempts == 1 and t_proof < message.next_delivery_attempt

    # Węzeł przekazuje ruch stacji przy odłączonym komputerze: dwie nowe stacje słyszą tylko węzeł.
    RNS.Reticulum.panic_on_interface_error = False
    kiss.detach()
    first = programs.add("first", near=("node",))
    second = programs.add("second", near=("node",))
    first.command("announce 57494349")
    second.command("announce 57494349")
    first_address, second_address = first.ready["address"], second.ready["address"]
    checks["node_forwards_without_computer"] = (first.wait("announce", 180, lambda e: e["dest"] == second_address) is not None
                                                and second.wait("announce", 180, lambda e: e["dest"] == first_address) is not None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--debt", type=int, default=12, help="silence debt factor of the emulated P1 link")
    parser.add_argument("--port", type=int, help="first of two UDP ports (default: two free ports from the system)")
    parser.add_argument("--lxmf", action="store_true", help="station core: lxmf.delivery and LXMF SA1 messages (stage R4b)")
    parser.add_argument("--link", choices=("p1", "lora"), default="p1", help="link between the programs: emulated P1 or LoRa (frames)")
    parser.add_argument("--bitrate", type=int, default=None,
                        help="bitrate of the computer KISS interface in the Reticulum config (bit/s); it sets the receipt "
                             "timeouts: 500 B x 8 / bitrate + 6 s + 6 s per hop (default 24, with --link lora 41)")
    args = parser.parse_args()
    lora = args.link == "lora"
    if lora and not args.lxmf:
        parser.error("--link lora needs --lxmf")
    if args.bitrate is None:
        args.bitrate = LORA_BITRATE if lora else 24
    global APP_NAME, ASPECT
    if args.lxmf:
        APP_NAME, ASPECT = "lxmf", "delivery"

    import RNS  # noqa: E402 (needs the reference Reticulum)
    import udp_ports  # noqa: E402 (tools/udp_ports.py)
    import sa1_lxmf  # noqa: E402 (tools/sa1_lxmf.py)

    work = tempfile.mkdtemp(prefix="wici_osp_node_")
    station_port, node_port = (args.port, args.port + 1) if args.port else udp_ports.free_udp_ports(2)
    results = {"reticulum": "e40191b", "debt_factor": args.debt, "bitrate": args.bitrate, "checks": {}}
    checks = results["checks"]
    node_fram = os.path.join(work, "node.bin")
    air = Air() if lora else None
    link = args.link
    node_peer, station_peer = (air.add("node", node_port), air.add("station", station_port)) if lora else (station_port, node_port)
    if lora:
        air.link("node", "station")
    node = Program(args.program, node_fram, node_port, node_peer, args.debt, node=True, link=link)
    station = Program(args.program, os.path.join(work, "station.bin"), station_port, station_peer, args.debt, link=link)
    programs = Programs(args, work, air, link) if lora else None
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
            def run_burst(size, quiet_s):
                """Seria size pakietów z komputera; kończy, gdy dotarły wszystkie albo przez quiet_s nic nowego."""
                before = node.status()
                burst = [b'["WICI",1,"osp node","burst %d of %d"]' % (i, size) for i in range(size)]
                t0 = time.time()
                for data in burst:
                    RNS.Packet(out, incoming(out, data)).send()
                flowed = wait_for(lambda: not kiss.packet_queue and kiss.interface_ready, 30)
                queue_empty_s = round(time.time() - t0, 2)
                got = set()
                last = time.time()
                while len(got) < size and time.time() - last < quiet_s:
                    e = station.wait("packet", 1)
                    for data in burst:
                        if e and delivered(e, data) and data not in got:
                            got.add(data)
                            last = time.time()
                after = node.status()
                return flowed, queue_empty_s, got, {
                    "sent": size, "received": len(got), "usb_rns_in": after.get("usb_rns_in", 0) - before.get("usb_rns_in", 0),
                    "usb_ready": after.get("usb_ready", 0) - before.get("usb_ready", 0),
                    "usb_rx_drop": after.get("usb_rx_drop", 0) - before.get("usb_rx_drop", 0),
                    "usb_k1": after.get("usb_k1", 0) - before.get("usb_k1", 0), "seconds": round(time.time() - t0, 2)}

            flowed, queue_empty_s, got, burst_result = run_burst(BURST, 300)
            results["burst"], results["burst_queue_empty_s"] = burst_result, queue_empty_s
            checks["burst_without_flow_timeout"] = flowed and queue_empty_s < 4
            checks["burst_delivered_without_drops"] = len(got) == BURST and burst_result["usb_rx_drop"] == 0
            if args.lxmf:
                # Pakiety od komputera na P1 w klasie K1 (rdzeń liczy je w usb_k1).
                checks["computer_packets_k1"] = burst_result["usb_k1"] >= BURST
        else:
            for name in ("computer_to_station_packet", "computer_receipt_delivered", "burst_without_flow_timeout",
                         "burst_delivered_without_drops"):
                checks[name] = False
        if lora:
            lora_checks(args, work, air, programs, node, station, kiss, identity, destination, station_identity, station_address,
                        node_port, seen, results, checks, wait_for, sa1_lxmf)
        elif args.lxmf:
            flood(node, station, kiss, results, checks, lambda content: (outgoing(content), computer_sa1),
                  lambda content: wait_for(lambda: any(carried(p, content) for p in seen["packets"]), 120))
            cheap_flood(node, station, kiss, results, checks, lambda: sum(1 for a in seen["announces"] if a[1] == station_address))
            extra = computer_destinations(node, kiss, destination, node_port, results, checks, wait_for)
        results["node_status"] = node.status()
        if args.lxmf and not lora:
            # Cele komputera także po restarcie węzła: 8 najnowszych tras przez USB o 1 skoku z tablicy w FRAM.
            # Koniec programu węzła zamyka pty (w Linuksie EIO w KISSInterface, przy panic_on_interface_error
            # koniec procesu), więc najpierw komputer odłącza interfejs, jak Reticulum przy wyjściu (detach,
            # bez ponownego łączenia z pty o tej samej nazwie); panika wyłączona przed detach, bo zamknięcie
            # portu przerywa wątek odczytu wyjątkiem. Dalsze sprawdzenia pytają tylko program węzła.
            RNS.Reticulum.panic_on_interface_error = False
            kiss.detach()
            node.stop()
            node = Program(args.program, node_fram, node_port, station_port, args.debt, node=True)
            time.sleep(2)   # po przeglądzie tras (raz na sekundę): trasy z FRAM nie wygasają po restarcie

            def pinned_after(dest):
                node.command(f"pinned {dest.hex()}")
                return (node.wait("pinned", 5) or {}).get("pinned") is True
            after_restart = [pinned_after(d.hash) for d in extra] + [pinned_after(destination.hash)]
            results["pinned_after_restart"] = {"extra": after_restart[:-1], "computer": after_restart[-1],
                                               "usb_pinned": node.status().get("usb_pinned")}
            checks["computer_destinations_after_restart"] = all(after_restart[:-1]) and not after_restart[-1]
    finally:
        # Koniec programu węzła zamyka pty: w Linuksie interfejs KISS dostaje EIO i przy panic_on_interface_error
        # Reticulum kończy proces (os._exit) przed wypisaniem wyniku. Panika obejmuje tylko samą próbę.
        RNS.Reticulum.panic_on_interface_error = False
        node.stop()
        station.stop()
        if programs:
            programs.stop()

    results["passed"] = all(checks.values())
    print(json.dumps(results, indent=2, default=str))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
