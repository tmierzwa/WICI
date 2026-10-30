# SPDX-License-Identifier: MIT
"""Receiving station application (software/laptop/wici/stanowisko, PLAN.md stages S1-S10).

The unit tests run with any Python. The stack test (S1) runs the application stack in this process
behind two "host" programs of the firmware (station and OSP node on the emulated radio link, the node USB
data port as a pseudo-terminal), like firmware/tools/rns_osp_node.py, and needs Reticulum at e40191b,
LXMF at c3ff2d6 and pyserial in this Python, and the built program:

  pio run -e host -d firmware
  WICI_HOST_PROGRAM=firmware/.pio/build/host/program /path/to/venv/bin/python -m unittest tests.test_stanowisko
"""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import tempfile
import time
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
sys.path.insert(0, str(ROOT / "firmware" / "tools"))

from wici.stanowisko import __main__ as aplikacja, przyjecie, stos, wysylka, wzorzec  # noqa: E402

PROGRAM = os.environ.get("WICI_HOST_PROGRAM")
HAS_STACK = all(importlib.util.find_spec(m) for m in ("RNS", "LXMF", "serial"))


class ConfigTest(unittest.TestCase):
    def test_one_kiss_interface_without_transport_or_shared_instance(self):
        text = stos.config("/dev/ttyACM0")
        self.assertIn("enable_transport = No", text)
        self.assertIn("share_instance = No", text)
        self.assertIn("type = KISSInterface", text)
        self.assertIn("port = /dev/ttyACM0", text)
        self.assertIn("flow_control = Yes", text)
        self.assertIn(f"bitrate = {stos.BITRATE}", text)
        self.assertEqual(text.count("type = "), 1)   # bez AutoInterface, TCP i UDP
        # Awaria portu nie kończy procesu (panic): interfejs KISS łączy się ponownie, a aplikacja działa dalej.
        self.assertIn("panic_on_interface_error = No", text)

    def test_bitrate_meets_the_radio_criterion(self):
        # radio.md, kryterium bitrate: 500 B × 8 / bitrate nie krócej niż odstęp dla 2 skoków z modelu.
        model = json.loads((ROOT / "software" / "reference" / "wyniki.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(500 * 8 / stos.BITRATE, model["lxmf_retry"]["2_hop_min_interval_worst_debt_full_queue_s"])

    def test_rejects_values_that_would_break_the_config(self):
        for bad in (0, 1201, -5):
            with self.assertRaises(ValueError):
                stos.config("/dev/ttyACM0", bad)
        for bad in ("COM5\n[[x]]", "a]b"):
            with self.assertRaises(ValueError):
                stos.config(bad)


def request(mid=None, revision=1, kind=0, people=3, text="piwnica"):
    """SA1 content of a REQUEST (kind 0) or TEST (kind 5)."""
    return wzorzec.encode_message([1, kind, mid or secrets.token_hex(16), revision, 2, people, "ul. Długa 5", text, 1])


def received_for(content):
    value = wzorzec.decode_message(content)
    return wzorzec.encode_message([1, 1, value[2], value[3], 1, 1])


class Sent:
    """A message handed to the fake stack; result is its outcome (True DELIVERED, False FAILED, None in flight)."""

    def __init__(self, result):
        self.result = result


class StationTestCase(unittest.TestCase):
    """Przyjecie with a fake stack, a clock set by the test and jitter 1.0 (random 0.5)."""

    STATION, OTHER = bytes(range(16)), bytes(range(16, 32))
    KEY = bytes(64)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "baza.sqlite"
        self.sent, self.committed = [], []
        self.now = 1_800_000_000.0
        self.result = True   # wynik kolejnych wysyłek; "brak trasy" to send zwracające None
        self.reception = self.open()
        self.reception.call(lambda s: s.add_trusted(self.STATION, self.KEY, ("dyzurny-1", "dyzurny-2")))

    def open(self):
        return przyjecie.Przyjecie(self.path, self.send, lambda m: m.result, clock=lambda: self.now,
                                   log=lambda line: None, random=lambda: 0.5)

    def restart(self):
        self.reception.stop()
        self.reception = self.open()

    def tearDown(self):
        self.reception.stop()
        self.tmp.cleanup()

    def send(self, target, content):
        # Drugie połączenie z bazą widzi tylko zatwierdzone dane: wiadomość wychodzi po COMMIT.
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            value = wzorzec.decode_message(content)
            if value[1] == wysylka.RECEIVED:
                self.committed.append(db.execute("SELECT 1 FROM received WHERE source=? AND id=? AND revision=?",
                                                 (target, value[2], value[3])).fetchone() is not None)
        if self.result == "no path":
            return None
        self.sent.append((target, content))
        return Sent(self.result)

    def tick(self):
        self.reception.call(lambda s: self.reception.tick())

    def deliver(self, source, content):
        self.reception.deliver(source, content)
        self.tick()   # kolejka wątku bazy pusta, wyniki wysyłek w drodze odebrane

    def kinds(self):
        return [wzorzec.decode_message(c)[1] for _, c in self.sent]


class ReceptionTest(StationTestCase):
    """S2: reception on the reference OSPStore in its own thread; RECEIVED only after COMMIT."""

    def test_trusted_request_gets_received_after_commit_with_reception_time(self):
        content = request()
        self.deliver(self.STATION, content)
        self.assertEqual(self.sent, [(self.STATION, received_for(content))])
        self.assertEqual(self.committed, [True])
        value = wzorzec.decode_message(content)
        at = self.reception.call(lambda s: s.db.execute(
            "SELECT at FROM received_at WHERE source=? AND id=? AND revision=?", (self.STATION, value[2], value[3])).fetchone())
        self.assertEqual(at, (self.now,))

    def test_test_message_is_received_too(self):
        content = request(kind=5, people=1, text="")
        self.deliver(self.STATION, content)
        self.assertEqual(self.sent, [(self.STATION, received_for(content))])

    def test_repeated_request_gets_the_same_received_and_keeps_the_first_time(self):
        content = request()
        self.deliver(self.STATION, content)
        first = self.now
        self.now += 600
        self.deliver(self.STATION, content)
        self.assertEqual([s[1] for s in self.sent], [received_for(content)] * 2)
        self.assertEqual(self.reception.counts["received"], 1)
        self.assertEqual(self.reception.counts["duplicate"], 1)
        self.assertEqual(self.reception.call(lambda s: s.db.execute("SELECT at FROM received_at").fetchall()), [(first,)])

    def test_new_revision_is_a_separate_reception(self):
        mid = secrets.token_hex(16)
        self.deliver(self.STATION, request(mid, 1))
        self.deliver(self.STATION, request(mid, 2, people=5))
        self.assertEqual(self.reception.counts["received"], 2)
        self.assertEqual(len(self.sent), 2)

    def test_same_key_with_other_content_is_a_conflict_without_overwrite(self):
        mid = secrets.token_hex(16)
        self.deliver(self.STATION, request(mid, 1, people=3))
        self.deliver(self.STATION, request(mid, 1, people=4))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.reception.counts["rejected"], 1)
        payload = self.reception.call(lambda s: s.db.execute("SELECT payload FROM received").fetchone()[0])
        self.assertEqual(wzorzec.decode_message(payload)[5], 3)

    def test_unknown_station_goes_to_quarantine_without_received(self):
        self.deliver(self.OTHER, request())
        self.assertEqual(self.sent, [])
        self.assertEqual(self.reception.call(lambda s: s.db.execute("SELECT count(*) FROM quarantine").fetchone()[0]), 1)
        for _ in range(wzorzec.QUARANTINE_PER_SENDER):
            self.deliver(self.OTHER, request())
        self.assertEqual(self.reception.counts["quarantined"], wzorzec.QUARANTINE_PER_SENDER)
        self.assertEqual(self.reception.counts["quarantine_full"], 1)

    def test_removed_station_is_quarantined_and_counted(self):
        self.reception.call(lambda s: s.remove_trusted(self.STATION))
        self.deliver(self.STATION, request())
        self.deliver(self.STATION, request())
        self.assertEqual(self.sent, [])
        self.assertEqual(self.reception.call(lambda s: s.removed_messages(self.STATION)), 2)

    def test_invalid_content_and_other_message_types_are_rejected(self):
        self.deliver(self.STATION, b'["nie SA1"]')
        self.deliver(self.STATION, received_for(request()))   # RECEIVED nie jest zgłoszeniem
        self.assertEqual(self.sent, [])
        self.assertEqual(self.reception.counts["rejected"], 2)

    def test_database_error_before_commit_sends_nothing_and_keeps_working(self):
        self.reception.call(lambda s: s.db.execute("DROP TABLE received_at"))
        self.deliver(self.STATION, request())
        self.assertEqual(self.sent, [])
        self.assertEqual(self.reception.call(lambda s: s.db.execute("SELECT count(*) FROM received").fetchone()[0]), 0)
        self.reception.call(lambda s: s.db.executescript(przyjecie.SCHEMA))
        self.deliver(self.STATION, request())
        self.assertEqual(len(self.sent), 1)

    def test_database_survives_a_restart(self):
        content = request()
        self.deliver(self.STATION, content)
        self.restart()
        self.deliver(self.STATION, content)
        self.assertEqual(self.reception.counts["duplicate"], 1)
        self.assertEqual(self.sent[0], self.sent[1])


class SendingTest(StationTestCase):
    """S3: intents in SQLite, order, at most 4 in flight, retries after FAILED, `event` numbers, clock check."""

    def accepted(self):
        """A REQUEST of the station with its RECEIVED delivered; returns (id, revision)."""
        content = request()
        self.deliver(self.STATION, content)
        self.tick()
        return wzorzec.decode_message(content)[2:4]

    def status(self, mid, revision, state):
        return self.reception.call(lambda s: self.reception.wysylka.status(s, self.STATION, mid, revision, state, self.now))

    def waiting(self):
        return self.reception.call(lambda s: s.db.execute("SELECT count(*) FROM outbox WHERE done=0").fetchone()[0])

    def test_received_goes_out_after_commit_and_the_intent_ends_on_delivered(self):
        self.accepted()
        self.assertEqual(self.committed, [True])
        self.assertEqual(self.waiting(), 0)

    def test_retries_after_failed_as_the_station(self):
        self.result = False
        self.deliver(self.STATION, request())
        start, times = self.now, []
        while self.now - start < 8 * 3600:
            self.now += 10
            before = len(self.sent)
            self.tick()
            if len(self.sent) > before:
                times.append(self.now - start)
                self.tick()   # FAILED zaraz po nadaniu: odstęp liczy się od tej chwili
        gaps = [b - a for a, b in zip([0] + times, times)]
        self.assertEqual(gaps[:6], [60, 120, 300, 900, 900, 900])
        late = [g for t, g in zip(times, gaps) if t - g >= wysylka.LATE_AFTER_S]
        self.assertTrue(late and set(late) == {3600})
        self.assertEqual(len(self.sent), len(times) + 1)   # każde ponowienie to nowa wiadomość

    def test_retry_interval_has_twenty_percent_jitter(self):
        self.assertEqual(wysylka.retry_delay(1, 0, lambda: 0.0), 48)
        self.assertEqual(round(wysylka.retry_delay(3, 0, lambda: 0.999999)), 360)
        self.assertEqual(wysylka.retry_delay(9, 7 * 3600, lambda: 0.5), 3600)

    def test_no_path_counts_as_failed(self):
        self.result = "no path"
        self.deliver(self.STATION, request())
        self.result = True
        self.now += 59
        self.tick()
        self.assertEqual(self.sent, [])
        self.now += 1
        self.tick()
        self.assertEqual(self.kinds(), [wysylka.RECEIVED])

    def test_at_most_four_in_flight_and_received_before_reply(self):
        mid, revision = self.accepted()
        self.sent.clear()
        self.result = "no path"   # wszystko czeka na ponowienie po 60 s
        self.reception.call(lambda s: self.reception.wysylka.reply(s, self.STATION, mid, revision, "jedziemy", self.now))
        for _ in range(5):
            self.deliver(self.STATION, request())
        self.result = None        # nic nie wraca: wysłane zostają w drodze
        self.now += 60
        self.tick()
        self.assertEqual(self.kinds(), [wysylka.RECEIVED] * wysylka.IN_FLIGHT)
        for message, _ in list(self.reception.wysylka.flight.values()):
            message.result = True
        self.tick()
        self.assertEqual(self.kinds()[4:], [wysylka.RECEIVED, wysylka.REPLY])   # REPLY po RECEIVED

    def test_newer_status_replaces_one_not_yet_delivered(self):
        mid, revision = self.accepted()
        self.result = "no path"
        self.status(mid, revision, 2)
        self.tick()
        self.status(mid, revision, 3)
        self.result = True
        self.now += 60
        self.tick()
        self.tick()
        self.assertEqual([wzorzec.decode_message(c)[5] for _, c in self.sent[1:]], [3])
        self.assertEqual(self.waiting(), 0)

    def test_repeated_request_gets_received_and_the_newest_status(self):
        content = request()
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        self.status(mid, revision, 2)
        self.now += 5
        self.status(mid, revision, 4)
        self.tick()
        self.tick()
        self.sent.clear()
        self.deliver(self.STATION, content)
        self.assertEqual(self.sent[0][1], received_for(content))
        self.assertEqual(wzorzec.decode_message(self.sent[1][1])[4:], [int(self.now) - wysylka.EPOCH_2026, 4])

    def test_repeat_sends_a_waiting_intent_at_once(self):
        self.result = False
        content = request()
        self.deliver(self.STATION, content)
        self.result = True
        self.now += 30   # ponowienie dopiero po 60 s
        self.deliver(self.STATION, content)
        self.assertEqual(self.kinds(), [wysylka.RECEIVED] * 2)
        self.assertEqual(self.waiting(), 0)

    def test_intents_are_checked_while_the_panel_keeps_the_thread_busy(self):
        self.result = None
        self.deliver(self.STATION, request())
        message = next(iter(self.reception.wysylka.flight.values()))[0]
        message.result = True
        end = time.monotonic() + 3 * przyjecie.Przyjecie.TICK_S
        while self.waiting() and time.monotonic() < end:   # call() bez przerwy, jak panel
            pass
        self.assertEqual(self.waiting(), 0)

    def test_restart_during_sending_sends_again(self):
        self.result = None
        self.deliver(self.STATION, request())
        self.restart()
        self.result = True
        self.tick()
        self.assertEqual(self.kinds(), [wysylka.RECEIVED] * 2)
        self.tick()
        self.assertEqual(self.waiting(), 0)

    def test_event_numbers(self):
        mid, revision = self.accepted()
        seconds = int(self.now) - wysylka.EPOCH_2026
        self.assertEqual(self.status(mid, revision, 2), seconds)
        self.assertEqual(self.status(mid, revision, 3), seconds + 1)   # ta sama sekunda: licznik + 1
        reply = lambda: self.reception.call(lambda s: self.reception.wysylka.reply(s, self.STATION, mid, revision, "x", self.now))
        self.assertEqual(reply(), seconds)                             # osobny licznik REPLY tego id
        bulletin = lambda: self.reception.call(lambda s: self.reception.wysylka.bulletin(s, "komunikat", self.now))
        bulletin(), bulletin()
        events = self.reception.call(lambda s: s.db.execute(
            "SELECT payload FROM outbox WHERE kind=4 ORDER BY seq").fetchall())
        self.assertEqual([wzorzec.decode_message(p)[3] for (p,) in events], [seconds, seconds + 1])
        def offset(store):
            with store.db:
                store.db.execute("INSERT INTO settings VALUES('p', 86400)")   # P po odzyskaniu (etap S6)
        self.reception.call(offset)
        self.assertEqual(self.status(mid, revision, 4), seconds + 86400)

    def test_status_starts_at_two_before_2026(self):
        mid, revision = self.accepted()
        self.now = wysylka.EPOCH_2026 - 3600.0
        self.assertEqual(self.status(mid, revision, 2), 2)

    def test_failed_status_leaves_no_counter_or_intent(self):
        mid, revision = self.accepted()
        with self.assertRaises(ValueError):
            self.status(mid, revision, 5)   # stan 5 tylko po REPLY
        counters = self.reception.call(lambda s: s.db.execute("SELECT count(*) FROM counters").fetchone()[0])
        self.assertEqual((counters, self.waiting()), (0, 0))

    def test_bulletin_goes_to_every_trusted_station(self):
        self.reception.call(lambda s: s.add_trusted(self.OTHER, self.KEY, ("dyzurny-1", "dyzurny-2")))
        mid = self.reception.call(lambda s: self.reception.wysylka.bulletin(s, "komunikat", self.now))
        self.tick()
        self.assertEqual(sorted(t for t, _ in self.sent), [self.STATION, self.OTHER])
        self.assertEqual({wzorzec.decode_message(c)[2] for _, c in self.sent}, {mid})

    def test_start_is_refused_when_the_clock_is_behind_the_last_message(self):
        mid, revision = self.accepted()
        self.status(mid, revision, 2)
        self.reception.stop()
        self.now -= 60
        with self.assertRaises(wysylka.ClockBehind):
            self.reception = self.open()
        self.now += 60
        self.reception = self.open()   # ten sam czas: start przechodzi

    def test_application_reports_the_clock_and_does_not_start(self):
        mid, revision = self.accepted()
        self.status(mid, revision, 2)
        state = Path(self.tmp.name)   # self.path to baza.sqlite w tym katalogu
        out = io.StringIO()
        with unittest.mock.patch.object(przyjecie.time, "time", lambda: self.now - 3600), \
                contextlib.redirect_stdout(out):
            code = aplikacja.main(["--port", "brak", "--stan", str(state)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["event"], "clock_behind")


class StackHoldTest(unittest.TestCase):
    """S2: a message from a sender LXMF does not know yet waits, with a path request, until its identity arrives."""

    class Message:
        def __init__(self, source, content, validated, reason=None, title="SA1", forged=False):
            self.source_hash, self.content, self.signature_validated = source, content, validated
            self.unverified_reason, self.title, self.packed = reason, title, (source, content, forged)

        def title_as_string(self):
            return self.title

    def setUp(self):
        import types
        self.requests, self.known = [], set()
        lxmessage = types.SimpleNamespace(SOURCE_UNKNOWN=1, SIGNATURE_INVALID=2,
                                          unpack_from_bytes=lambda packed: self.Message(
                                              packed[0], packed[1], packed[0] in self.known and not packed[2]))
        rns = types.SimpleNamespace(Transport=types.SimpleNamespace(request_path=self.requests.append),
                                    Identity=types.SimpleNamespace(recall=lambda h: object() if h in self.known else None))
        self.modules = unittest.mock.patch.dict(sys.modules, {"LXMF": types.SimpleNamespace(LXMessage=lxmessage), "RNS": rns})
        self.modules.start()
        self.got = []
        self.stos = stos.Stos(tempfile.gettempdir(), "port", lambda s, c: self.got.append((s, c)), log=lambda line: None)

    def tearDown(self):
        self.modules.stop()

    def test_checked_message_goes_on_at_once(self):
        self.stos._delivered(self.Message(b"A" * 16, b"x", True))
        self.assertEqual(self.got, [(b"A" * 16, b"x")])

    def test_unknown_sender_waits_for_its_announce(self):
        source = b"A" * 16
        self.stos._delivered(self.Message(source, b"x", False, reason=1))
        self.assertEqual((self.got, self.requests), ([], [source]))
        self.known.add(source)
        self.stos.received_announce(source, None, None)
        self.assertEqual(self.got, [(source, b"x")])
        self.assertEqual(self.stos.pending, {})

    def test_forged_signature_after_the_announce_is_dropped(self):
        source = b"A" * 16
        self.stos._delivered(self.Message(source, b"x", False, reason=1, forged=True))
        self.stos._delivered(self.Message(source, b"y", False, reason=2))   # SIGNATURE_INVALID od razu
        self.known.add(source)
        self.stos.received_announce(source, None, None)
        self.assertEqual(self.got, [])
        self.assertEqual(self.stos.dropped["bad_signature"], 2)

    def test_waiting_messages_have_the_quarantine_limits(self):
        for i in range(stos.Stos.PENDING_PER_SENDER + 1):
            self.stos._delivered(self.Message(b"A" * 16, b"%d" % i, False, reason=1))
        self.assertEqual(len(self.stos.pending[b"A" * 16]), stos.Stos.PENDING_PER_SENDER)
        self.assertEqual(self.stos.dropped["pending_full"], 1)

    def test_other_titles_are_not_sa1(self):
        self.stos._delivered(self.Message(b"A" * 16, b"x", True, title="chat"))
        self.assertEqual(self.got, [])


@unittest.skipUnless(PROGRAM and HAS_STACK, "WICI_HOST_PROGRAM or Reticulum, LXMF and pyserial not available")
class StackTest(unittest.TestCase):
    """S1 and S2: the application behind the OSP node, with a station that has the application as card receiver."""

    @classmethod
    def setUpClass(cls):
        import rns_osp_node
        import udp_ports
        cls.work = tempfile.TemporaryDirectory()
        work = Path(cls.work.name)
        station_port, node_port = udp_ports.free_udp_ports(2)
        cls.node = rns_osp_node.Program(PROGRAM, str(work / "node.bin"), node_port, station_port, 12, node=True)
        cls.station = rns_osp_node.Program(PROGRAM, str(work / "station.bin"), station_port, node_port, 12)
        if not cls.node.ready or not cls.station.ready:
            raise RuntimeError("host programs did not start")
        cls.station_address = bytes.fromhex(cls.station.ready["address"])
        cls.station_announced_before_the_application()
        cls.messages = []

        def received(source, content):
            cls.messages.append((source, content))
            cls.reception.deliver(source, content)
        cls.stos = stos.Stos(work / "stan", cls.node.ready["usb"], received, log=lambda line: None)
        cls.reception = przyjecie.Przyjecie(work / "stan" / "baza.sqlite", cls.stos.send, cls.stos.outcome,
                                            log=lambda line: None)
        cls.stos.start()
        cls.station.command(f"receiver {cls.sa1_destination().hex()} {cls.stos.identity.get_public_key().hex()}")
        if cls.station.wait("receiver", 5) is None:
            raise RuntimeError("station did not take the application as card receiver")

    @classmethod
    def station_announced_before_the_application(cls):
        """The node knows the station from its announce, the application does not (a spare computer with empty
        Reticulum storage). Until the application connects, a plain reader empties the node USB port."""
        import serial
        port = serial.Serial(cls.node.ready["usb"], 115200, timeout=0.1)
        stop = threading.Event()
        reader = threading.Thread(target=lambda: [port.read(4096) for _ in iter(stop.is_set, True)], daemon=True)
        reader.start()
        cls.station.command("announce 57494349")
        known = False
        for _ in range(60):
            if cls.node.status().get("paths", 0) >= 1:
                known = True
                break
            time.sleep(0.5)
        stop.set()
        reader.join()
        port.close()
        if not known:
            raise RuntimeError("the node did not learn the station announce")

    @classmethod
    def tearDownClass(cls):
        import RNS
        RNS.Reticulum.panic_on_interface_error = False
        cls.stos.stop()
        cls.reception.stop()
        cls.node.stop()
        cls.station.stop()
        cls.work.cleanup()

    @staticmethod
    def wait_for(condition, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False

    @classmethod
    def sa1_destination(cls):
        import sa1_lxmf
        return sa1_lxmf.sa1_of(cls.stos.identity)

    def report(self, content):
        """content from the station through the node; True when the application got it (checked signature)."""
        import sa1_lxmf
        data = sa1_lxmf.envelope(self.station_address, self.sa1_destination(), content)
        self.station.command(f"send {self.sa1_destination().hex()} {data.hex()} 120")
        sent = self.station.wait("sent", 10)
        self.assertTrue(sent and sent["handle"] > 0)
        receipt = self.station.wait("receipt", 180, lambda e: e["handle"] == sent["handle"])
        self.assertTrue(receipt and receipt["delivered"])
        return self.wait_for(lambda: (self.station_address, content) in self.messages, 120)

    def received_at_station(self, content, timeout=120):
        import sa1_lxmf
        expected = sa1_lxmf.envelope(self.sa1_destination(), self.station_address, received_for(content)).hex()
        return self.station.wait("packet", timeout, lambda e: e["data"] == expected) is not None

    def test_1_flow_control_and_bitrate_from_config(self):
        import RNS
        self.assertTrue(self.wait_for(lambda: self.node.status().get("usb_flow") is True, 10))
        kiss = next(i for i in RNS.Transport.interfaces if type(i).__name__ == "KISSInterface")
        self.assertEqual(kiss.bitrate, stos.BITRATE)
        self.assertFalse(RNS.Reticulum.transport_enabled())

    def test_2_announce_reaches_the_station(self):
        self.stos.announce()
        self.assertIsNotNone(self.station.wait("announce", 120, lambda e: e["dest"] == self.stos.address.hex()))

    def test_3_station_off_the_trusted_list_is_quarantined_without_received(self):
        # Aplikacja startuje bez znajomości stacji; tożsamość przychodzi z ogłoszenia w pamięci węzła (po
        # połączeniu albo w odpowiedzi na zapytanie o trasę, StackHoldTest) i dopiero wtedy podpis jest sprawdzony.
        content = request(text="przed ogłoszeniem")
        self.assertTrue(self.report(content))
        self.assertEqual(self.reception.call(lambda s: s.db.execute(
            "SELECT count(*) FROM quarantine WHERE source=?", (self.station_address,)).fetchone()[0]), 1)
        self.assertFalse(self.received_at_station(content, timeout=5))

    def test_4_trusted_station_gets_received_and_again_for_a_repeat(self):
        import RNS
        identity = RNS.Identity.recall(self.station_address)
        self.assertIsNotNone(identity)
        self.reception.call(lambda s: s.add_trusted(self.station_address, identity.get_public_key(), ("dyzurny-1", "dyzurny-2")))
        content = request(text="zaufana stacja")
        self.assertTrue(self.report(content))
        self.assertTrue(self.received_at_station(content))
        # Dopiero po DELIVERED: powtórzenie w czasie wysyłki tylko przyspiesza intencję, która jest w drodze.
        self.assertTrue(self.wait_for(lambda: self.reception.call(lambda s: s.db.execute(
            "SELECT count(*) FROM outbox WHERE done=0").fetchone()[0]) == 0, 300))
        self.messages.clear()
        self.assertTrue(self.report(content))      # ponowione zgłoszenie (nowa wiadomość LXMF)
        self.assertTrue(self.received_at_station(content))
        self.assertEqual(self.reception.counts["duplicate"], 1)

    def test_5_application_message_reaches_the_station_and_is_delivered(self):
        import LXMF
        import sa1_lxmf
        content = b'["WICI",1,"stanowisko","aplikacja do stacji"]'
        message = self.stos.send(self.station_address, content)
        self.assertIsNotNone(message)
        expected = sa1_lxmf.envelope(self.sa1_destination(), self.station_address, content).hex()
        self.assertIsNotNone(self.station.wait("packet", 120, lambda e: e["data"] == expected))
        self.assertTrue(self.wait_for(lambda: message.state == LXMF.LXMessage.DELIVERED, 240))

    def test_6_identity_survives_a_restart(self):
        import RNS
        path = Path(self.work.name) / "stan" / "tozsamosc"
        self.assertEqual(RNS.Identity.from_file(str(path)).hash, self.stos.identity.hash)
        self.assertEqual(stos.Stos._identity(path).hash, self.stos.identity.hash)
        if sys.platform != "win32":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)   # klucz prywatny tylko dla użytkownika


if __name__ == "__main__":
    unittest.main()
