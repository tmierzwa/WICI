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
import shutil
import sqlite3
import sys
import tarfile
import threading
import tempfile
import time
import unittest
import unittest.mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
sys.path.insert(0, str(ROOT / "software" / "laptop" / "build"))

import build_stanowisko  # noqa: E402
from wici import database  # noqa: E402
from wici.stanowisko import __main__ as aplikacja, bearers, kopie, nosnik, panel, przyjecie, rekey, stos, wezel, wysylka, wzorzec, zamkniecie  # noqa: E402

PROGRAM = os.environ.get("WICI_HOST_PROGRAM")
# Pakiet stanowiska (build_stanowisko.py): SimulatorTest uruchamia wtedy aplikację jego skryptem stanowisko.sh.
PACKAGE = os.environ.get("WICI_STANOWISKO_PACKAGE")
HAS_STACK = all(importlib.util.find_spec(m) for m in ("RNS", "LXMF", "serial"))
FAST = 1_000   # iteracje PBKDF2 w testach (najmniej, ile przyjmuje odczyt)


def medium_in(root, officers=2, identity=None):
    """A prepared medium with fast PBKDF2: (medium, data key, envelopes)."""
    return nosnik.Nosnik.create(root, officers, identity or bytes(range(64)), FAST)


def durable(medium, key, sql, args=()):
    """Query the medium as a restarted application would see it: the newest snapshot and the receptions of the
    intake journal admitted again, on a copy of the medium, so the running application is not touched."""
    if nosnik.Nosnik(medium.root).load(key) is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "nosnik"
        shutil.copytree(medium.root, copy, ignore=shutil.ignore_patterns("*.tmp"))
        restarted = przyjecie.Przyjecie(nosnik.Nosnik(copy, FAST), key, lambda target, content: None,
                                        lambda message: None, clock=lambda: 4_000_000_000.0, log=lambda line: None)
        try:
            return restarted.call(lambda store: store.db.execute(sql, args).fetchone())
        finally:
            restarted.stop(save=False)


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


class BearerSetTest(unittest.TestCase):
    def test_reply_follows_last_authenticated_bearer_and_preserves_outcome(self):
        class Fake:
            address = bytes(16)

            def __init__(self):
                self.sent = []

            def send(self, dest, content):
                self.sent.append((dest, content))
                return Sent(True)

            def outcome(self, item):
                return item.result

            def start(self): pass
            def stop(self): pass
            def announce(self): pass
            def status(self, now):
                return {"online": True, "since_rx": 0, "dropped": {}}

        wici, legacy = Fake(), Fake()
        collection = bearers.Bearers({"wici": wici, "reticulum": legacy}, "wici")
        source = bytes(range(16))
        class Reception:
            last_bearer = {}
            bearer_override = {}

            @staticmethod
            def send_wici(bearer, dest, content):
                return bearer.send(dest, content)

        collection.reception = Reception()
        first = collection.send(source, b"reply")
        self.assertEqual(first.bearer, "wici")
        self.assertTrue(collection.outcome(first))
        collection.reception.last_bearer[source] = "reticulum"
        second = collection.send(source, b"reply2")
        self.assertEqual(second.bearer, "reticulum")
        self.assertEqual(wici.sent, [(source, b"reply")])
        self.assertEqual(legacy.sent, [(source, b"reply2")])
        self.assertTrue(collection.outcome(second))
        collection.reception.last_bearer.clear()
        collection.reception.send_wici = lambda *_: None
        third = collection.send(source, b"fallback")
        self.assertEqual(third.bearer, "reticulum")
        self.assertEqual(legacy.sent[-1], (source, b"fallback"))
        collection.reception.bearer_override[source] = "wici"
        self.assertIsNone(collection.send(source, b"operator-choice"))
        collection.reception.send_wici = Reception.send_wici
        collection.reception.bearer_override[source] = "wici"
        collection.reception.last_bearer[source] = "reticulum"
        self.assertEqual(collection.send(source, b"manual").bearer, "wici")

        # A failed delivery on the remembered bearer sends the next attempt on the other one.
        collection.reception.bearer_override.clear()
        collection.reception.last_bearer[source] = "wici"
        failed = collection.send(source, b"lost")
        failed.message.result = False
        self.assertFalse(collection.outcome(failed))
        retry = collection.send(source, b"lost")
        self.assertEqual(retry.bearer, "reticulum")
        self.assertTrue(collection.outcome(retry))
        self.assertEqual(collection.send(source, b"next").bearer, "wici")
        collection.reception.bearer_override[source] = "wici"
        failed = collection.send(source, b"operator")
        failed.message.result = False
        collection.outcome(failed)
        self.assertEqual(collection.send(source, b"operator").bearer, "wici")   # the operator's choice holds


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
        self.medium, self.key, self.envelopes = medium_in(Path(self.tmp.name) / "nosnik")
        self.sent, self.committed = [], []
        self.now = 1_800_000_000.0
        self.result = True   # wynik kolejnych wysyłek; "brak trasy" to send zwracające None
        self.reception = self.open()
        self.reception.call(lambda s: s.add_trusted(self.STATION, self.KEY, ("dyzurny-1", "dyzurny-2")))

    def open(self):
        return przyjecie.Przyjecie(self.medium, self.key, self.send, lambda m: m.result, clock=lambda: self.now,
                                   log=lambda line: None, random=lambda: 0.5)

    def restart(self):
        self.reception.stop()
        self.reception = self.open()

    def tearDown(self):
        self.reception.stop()
        self.tmp.cleanup()

    def send(self, target, content):
        # Migawka na nośniku musi już mieć zgłoszenie: wiadomość wychodzi po COMMIT i po zapisie na nośniku.
        value = wzorzec.decode_message(content)
        if value[1] == wysylka.RECEIVED:
            self.committed.append(durable(self.medium, self.key, "SELECT 1 FROM received WHERE source=? AND id=? "
                                          "AND revision=?", (target, value[2], value[3])) is not None)
        if self.result == "no path":
            return None
        self.sent.append((target, content))
        return Sent(self.result)

    def tick(self):
        # A tick and the writes it started (snapshot, copy), so the test sees their result.
        self.reception.call(lambda s: (self.reception.tick(), self.reception.flush()))

    def deliver(self, source, content):
        self.reception.deliver(source, content)
        self.tick()   # kolejka wątku bazy pusta, wyniki wysyłek w drodze odebrane

    def kinds(self):
        return [wzorzec.decode_message(c)[1] for _, c in self.sent]


class ReceptionTest(StationTestCase):
    """S2: reception on the reference OSPStore in its own thread; RECEIVED only after COMMIT."""

    def test_reticulum_route_updates_only_after_trusted_admission(self):
        self.reception.deliver(self.STATION, b"invalid", bearer="reticulum")
        self.tick()
        self.assertIsNone(self.reception.call(lambda s: self.reception.last_bearer.get(self.STATION)))
        self.reception.deliver(self.STATION, request(), bearer="reticulum")
        self.tick()
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(self.STATION)), "reticulum")
        self.restart()
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(self.STATION)), "reticulum")
        content = request()
        self.reception.deliver(self.STATION, content, bearer="wici")
        self.reception.deliver(self.STATION, content, bearer="reticulum")   # repeat: the route stays
        self.tick()
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(self.STATION)), "wici")
        self.assertEqual(durable(self.medium, self.key, "SELECT bearer FROM bearer_route"), ("wici",))

    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography for D21 envelope")
    def test_numbered_envelope_fragments_commit_with_sa1_and_replay(self):
        from cryptography.hazmat.primitives.asymmetric import x25519
        from wici import envelope

        receiver_private = bytes(range(32))
        station_private = bytes(range(32, 64))
        receiver_public = x25519.X25519PrivateKey.from_private_bytes(receiver_private).public_key().public_bytes_raw()
        station_public = x25519.X25519PrivateKey.from_private_bytes(station_private).public_key().public_bytes_raw()
        main = nosnik.public_identity(receiver_private + bytes(range(32)))
        backup = bytes(range(64, 128))
        station_key = station_public + bytes(range(32, 64))
        source = nosnik.lxmf_address(station_key)
        self.medium.save_identity(self.key, receiver_private + bytes(range(32)))
        self.medium.save_card(self.key, nosnik.receiver_card(main, backup, 100, 2, 3))

        def register(store):
            store.add_trusted(source, station_key, ("dyzurny-1", "dyzurny-2"))
            store.db.execute("INSERT INTO numery VALUES(?,?,?,?)", (100, 4, source, station_key))

        self.reception.call(register)
        content = request(text="x" * 96)
        key = envelope.derive_key(station_private, receiver_public, 100, 4, 2, own_id=4)
        frames = envelope.seal(key, 4, 2, 7, content, 153)
        self.assertEqual(len(frames), 2)
        self.assertEqual(self.reception.receive_envelope_frame(100, frames[1], bearer="wici"), "partial")
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(source)), "wici")
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_parts"), (1,))
        self.restart()
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(source)), "wici")
        self.assertEqual(self.reception.receive_envelope_frame(100, frames[0], bearer="wici"), "complete")
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))
        self.assertEqual(durable(self.medium, self.key, "SELECT highest FROM env_replay"), (7,))
        self.assertEqual(self.reception.receive_envelope_frame(100, frames[0]), "duplicate")
        # A replayed frame is acknowledged again but does not move the reply route.
        self.assertEqual(self.reception.receive_envelope_frame(100, frames[0], bearer="reticulum"), "duplicate")
        self.assertIsNone(durable(self.medium, self.key, "SELECT 1 FROM bearer_route WHERE bearer='reticulum'"))
        with self.assertRaises(przyjecie.NotAuthenticated):
            self.reception.receive_envelope_frame(101, frames[0])
        forged = bytearray(frames[0]); forged[-1] ^= 1
        with self.assertRaises(przyjecie.NotAuthenticated):
            self.reception.receive_envelope_frame(100, forged, bearer="reticulum")
        self.assertEqual(self.reception.call(lambda s: self.reception.last_bearer.get(source)), "wici")

    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography for D21 envelope")
    def test_numbered_outbound_reserves_counter_before_sealing(self):
        from cryptography.hazmat.primitives.asymmetric import x25519
        from wici import envelope

        receiver_private, station_private = bytes(range(32)), bytes(range(32, 64))
        receiver_public = x25519.X25519PrivateKey.from_private_bytes(receiver_private).public_key().public_bytes_raw()
        station_public = x25519.X25519PrivateKey.from_private_bytes(station_private).public_key().public_bytes_raw()
        station_key = station_public + bytes(range(32, 64))
        self.medium.save_identity(self.key, receiver_private + bytes(range(32)))
        self.medium.save_card(self.key, nosnik.receiver_card(nosnik.public_identity(receiver_private + bytes(range(32))), bytes(range(64, 128)), 100, 2, 3))
        def register(store):
            source = nosnik.lxmf_address(station_key)
            store.add_trusted(source, station_key, ("dyzurny-1", "dyzurny-2"))
            store.db.execute("INSERT INTO numery VALUES(?,?,?,?)", (100, 4, source, station_key))
        self.reception.call(register)
        content = received_for(request())
        source = nosnik.lxmf_address(station_key)

        class Link:
            network = 100
            frames = None

            def status(self, now):
                return {"online": True, "room": True}

            def send_frames(self, frames):
                self.frames = frames
                return frames

        def send(link):
            return self.reception.call(lambda s: self.reception.send_wici(link, source, content))

        first = send(Link())[0]
        self.assertEqual(durable(self.medium, self.key, "SELECT reserved_until FROM env_send"), (64,))
        self.restart()
        second = send(Link())[0]
        self.assertEqual((int.from_bytes(first[5:9], "big"), int.from_bytes(second[5:9], "big")), (0, 64))
        key = envelope.derive_key(station_private, receiver_public, 100, 2, 4, 4)
        self.assertEqual(envelope.open_part(key, second).plaintext, content)
        # Blocked after a recovery: no counter, no frame, so bearers.Bearers may use Reticulum.
        self.reception.call(lambda s: s.db.execute("INSERT INTO env_send_guard VALUES(1,1)"))
        blocked = Link()
        self.assertIsNone(send(blocked))
        self.assertIsNone(blocked.frames)
        self.assertEqual(durable(self.medium, self.key, "SELECT reserved_until FROM env_send"), (128,))

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

    def test_calls_after_stop_fail_instead_of_waiting(self):
        self.reception.stop(save=False)   # jak ZNISZCZ DANE: żądanie panelu albo odczyt węzła po zatrzymaniu
        with self.assertRaises(RuntimeError):
            self.reception.action("", "cisza_wezel", "{}")

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

    def test_station_off_the_trusted_list_gets_only_received_until_trusted_again(self):
        content = request()
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        self.reception.call(lambda s: s.remove_trusted(self.STATION))
        before = len(self.sent)
        self.status(mid, revision, 2)
        self.reception.call(lambda s: self.reception.wysylka.reply(s, self.STATION, mid, revision, "jedziemy", self.now))
        self.now += 3600
        self.tick()
        self.assertEqual(self.sent[before:], [])   # held, not failed: no retries counted
        self.assertEqual(self.reception.call(lambda s: s.db.execute(
            "SELECT count(*), sum(attempts) FROM outbox WHERE done=0").fetchone()), (2, 0))
        self.deliver(self.STATION, content)   # the repeat still gets its RECEIVED, without content
        self.assertEqual(self.kinds()[before:], [wysylka.RECEIVED])
        self.reception.call(lambda s: s.add_trusted(self.STATION, self.KEY, ("dyzurny-1", "dyzurny-2")))
        self.tick()
        self.tick()
        self.assertEqual(self.kinds()[before + 1:], [wysylka.STATUS, wysylka.REPLY])
        self.assertEqual(self.waiting(), 0)

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

    def sends(self, hours):
        """Times (s from now) of every send within hours, each finished at once with self.result."""
        start, times = self.now, []
        while self.now - start < hours * 3600:
            self.now += 10
            before = len(self.sent)
            self.tick()
            if len(self.sent) > before:
                times.append(self.now - start)
                self.tick()
        return times

    def test_forwarded_stays_open_and_waits_out_the_relay_custody(self):
        # E1: a relay's HACK is no proof. The intent stays open; the next copy waits until the first one has
        # left the relay queue (30 min), then twice as long each time, up to 4 h, with no contact.
        self.result = wysylka.FORWARDED
        self.deliver(self.STATION, request())
        times = self.sends(14)
        gaps = [b - a for a, b in zip([0] + times, times)]
        self.assertEqual(gaps[:5], [2100, 4200, 8400, 14400, 14400])
        self.assertEqual(self.waiting(), 1)
        self.assertEqual(self.reception.call(lambda s: s.db.execute("SELECT forwarded FROM outbox").fetchone()[0]),
                         len(times) + 1)   # and the first send, at once after the REQUEST

    def test_flooded_stays_open_on_the_failure_schedule(self):
        self.result = wysylka.FLOODED
        self.deliver(self.STATION, request())
        times = self.sends(1)
        self.assertEqual([b - a for a, b in zip([0] + times, times)][:4], [60, 120, 300, 900])
        self.assertEqual(self.waiting(), 1)

    def test_contact_sends_open_intents_at_once(self):
        self.result = wysylka.FORWARDED
        self.deliver(self.STATION, request())
        self.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += 60
        self.reception.call(lambda s: self.reception.wysylka.contact(s.db, self.STATION))
        self.tick()
        self.assertEqual(len(self.sent), 2)
        self.tick()   # contact also restarts the custody floor: 1 again, not 2
        self.assertEqual(self.reception.call(lambda s: s.db.execute("SELECT forwarded FROM outbox").fetchone()[0]), 1)

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

    def test_reply_waits_for_the_proof_of_the_earlier_reply_of_its_request(self):
        # The station skips a REPLY with an event below the one it took and proves it as late: an
        # overtaken REPLY would end as delivered without reaching the station. Other requests do not wait.
        other, _ = self.accepted()
        mid, revision = self.accepted()
        self.sent.clear()

        def reply(m, text):
            self.reception.call(lambda s: self.reception.wysylka.reply(s, self.STATION, m, revision, text, self.now))
        self.result = "no path"
        reply(mid, "pierwsza")
        self.tick()               # FAILED: ponowienie po 60 s
        self.now += 5
        reply(mid, "druga")
        reply(other, "inna")
        self.result = True
        self.tick()
        self.tick()
        self.assertEqual([wzorzec.decode_message(c)[5] for _, c in self.sent], ["inna"])
        self.now += 60
        for _ in range(3):
            self.tick()
        self.assertEqual([wzorzec.decode_message(c)[5] for _, c in self.sent], ["inna", "pierwsza", "druga"])
        self.assertEqual(self.waiting(), 0)

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
        out = io.StringIO()
        with unittest.mock.patch.object(przyjecie.time, "time", lambda: self.now - 3600), \
                unittest.mock.patch.object(sys, "stdin", io.StringIO(self.envelopes["stanowisko"] + "\n")), \
                contextlib.redirect_stdout(out):
            code = aplikacja.main(["start", "--nosnik", str(self.medium.root), "--port", "brak"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["event"], "clock_behind")


class MediumTest(unittest.TestCase):
    """S4: the medium with the station password, duty officer accounts, sealed snapshots and identities."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "nosnik"
        self.medium, self.key, self.envelopes = medium_in(self.root, officers=3)

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return b"".join(p.read_bytes() for p in self.root.rglob("*") if p.is_file())

    def test_station_password_opens_the_medium_on_another_computer(self):
        self.assertEqual(sorted(self.envelopes), ["dyzurny-1", "dyzurny-2", "dyzurny-3", "stanowisko"])
        self.assertEqual(len(self.envelopes["stanowisko"].split()), nosnik.STATION_WORDS)
        other = nosnik.Nosnik(self.root)   # drugi komputer: ten sam nośnik, bez magazynu systemu
        self.assertEqual(other.unlock("  " + self.envelopes["stanowisko"].upper() + " "), self.key)
        with self.assertRaises(database.LoginError):
            other.unlock("zle haslo")

    def test_failed_passwords_are_limited(self):
        for _ in range(database.LOGIN_LIMIT):
            with self.assertRaises(database.LoginError):
                self.medium.unlock("zle haslo")
        with self.assertRaisesRegex(database.LoginError, "Poczekaj"):
            self.medium.unlock(self.envelopes["stanowisko"])

    def test_new_station_password_rewraps_only_the_key(self):
        self.medium.save(self.key, b"baza")
        new = self.medium.new_station_password(self.key)
        self.assertEqual(nosnik.Nosnik(self.root).unlock(new), self.key)
        with self.assertRaises(database.LoginError):
            nosnik.Nosnik(self.root).unlock(self.envelopes["stanowisko"])
        self.assertEqual(nosnik.Nosnik(self.root).load(self.key), b"baza")

    def test_lost_account_file_does_not_lose_the_data(self):
        self.medium.save(self.key, b"baza")
        (self.root / "klucze" / database.ACCOUNTS).unlink()
        self.assertEqual(nosnik.Nosnik(self.root).unlock(self.envelopes["stanowisko"]), self.key)

    def test_duty_officer_accounts(self):
        self.medium.login("dyzurny-2", self.envelopes["dyzurny-2"], self.key)
        for name, password in (("dyzurny-2", self.envelopes["dyzurny-1"]), ("dyzurny-9", "x"),
                               ("stanowisko", self.envelopes["stanowisko"])):
            with self.assertRaises(database.LoginError):
                self.medium.login(name, password, self.key)
        new = self.medium.new_password("dyzurny-2", self.key)
        self.medium.login("dyzurny-2", new, self.key)
        with self.assertRaises(database.LoginError):
            self.medium.login("dyzurny-2", self.envelopes["dyzurny-2"], self.key)
        other, other_key, envelopes = medium_in(Path(self.tmp.name) / "inny")
        with self.assertRaises(database.LoginError):   # konto z innego nośnika
            self.medium.login("dyzurny-1", envelopes["dyzurny-1"], self.key)

    def test_snapshots_are_sealed_and_a_corrupt_newer_copy_fails_closed(self):
        self.medium.save(self.key, b"pierwsza piwnica")
        self.medium.save(self.key, b"druga piwnica")
        self.assertNotIn(b"piwnica", self.files())
        with unittest.mock.patch.object(nosnik.os, "replace", side_effect=OSError("zanik zasilania")):
            with self.assertRaises(OSError):
                self.medium.save(self.key, b"trzecia piwnica")
        self.assertEqual(nosnik.Nosnik(self.root).load(self.key), b"druga piwnica")   # przerwany zapis: tylko .tmp
        newest = self.root / "baza" / self.medium.last
        newest.write_bytes(newest.read_bytes()[:-10])   # uszkodzony nośnik: zapis zastępuje plik w całości
        with self.assertRaises(database.StorageError):
            nosnik.Nosnik(self.root).load(self.key)
        with self.assertRaises(database.StorageError):
            nosnik.Nosnik(self.root).load(os.urandom(32))

    def test_identity_is_sealed_with_the_data_key(self):
        self.assertEqual(self.medium.identity(self.key), bytes(range(64)))
        self.assertNotIn(bytes(range(64)), self.files())
        with self.assertRaises(database.StorageError):
            self.medium.identity(os.urandom(32))

    def test_numbered_link_binding_is_sealed_and_survives_reopen(self):
        link = {"net_id": 100, "root": 5, "ifac": "ab" * 16}
        self.medium.save_link(self.key, link)
        self.assertEqual(nosnik.Nosnik(self.root).link(self.key), {**link, "ttl": 7})
        self.assertNotIn(b"abababab", (self.root / "wici-link").read_bytes())
        with self.assertRaises(database.StorageError):
            self.medium.link(os.urandom(32))
        for bad in ({"root": 0}, {"ttl": 0}, {"ttl": 16}):
            with self.assertRaises(database.StorageError):
                self.medium.save_link(self.key, {**link, **bad})
        with self.assertRaises(database.StorageError):
            self.medium.save_link(self.key, {**link, "ifac": "ab " * 10 + "ab"})
        untouched = Path(self.tmp.name) / "invalid-link"
        with self.assertRaises(database.StorageError):
            nosnik.Nosnik.create(untouched, 2, bytes(range(64)), FAST,
                                 link={**link, "ifac": "not-a-network-code"})
        self.assertFalse(untouched.exists())

    def test_root_binding_cannot_silently_prepare_an_unnumbered_medium(self):
        with self.assertRaisesRegex(SystemExit, "--net-id"):
            aplikacja.prepare(unittest.mock.Mock(net_id=None, root_id=5, ifac=None))

    def test_a_prepared_medium_is_not_prepared_again(self):
        with self.assertRaises(database.StorageError):
            medium_in(self.root)

    def test_backup_package_opens_only_with_its_password(self):
        private, public = os.urandom(64), os.urandom(64)
        package = json.loads(json.dumps(nosnik.backup_package(private, public, "a b c d e f", FAST)))
        self.assertEqual(package["lxmf"], nosnik.lxmf_address(public).hex())
        self.assertNotIn(private.hex(), json.dumps(package))
        self.assertEqual(nosnik.open_backup(package, "A B C D E F"), private)
        with self.assertRaises(database.LoginError):
            nosnik.open_backup(package, "a b c d e g")
        with self.assertRaises(database.StorageError):
            nosnik.open_backup({**package, "v": 2}, "a b c d e f")

    def test_receiver_card_has_both_identities(self):
        main, backup = os.urandom(64), os.urandom(64)
        card = nosnik.receiver_card(main, backup)
        self.assertEqual((card["wici"], card["v"]), ("karta-odbiorcy", 1))
        self.assertEqual(card["backup"], {"lxmf": nosnik.lxmf_address(backup).hex(), "key": backup.hex()})
        self.assertEqual(card["main"]["key"], main.hex())
        numbered = nosnik.receiver_card(main, backup, 100, 2, 3)
        self.assertEqual(numbered["v"], 2)
        self.assertEqual(numbered["main"], {"lxmf": nosnik.lxmf_address(main).hex(), "key": main.hex(),
                                             "id": 2, "net_id": 100, "x25519": main[:32].hex()})
        with self.assertRaises(ValueError):
            nosnik.receiver_card(main, backup, 100, 2, 2)

    def test_database_lives_on_the_medium_only_sealed(self):
        reception = przyjecie.Przyjecie(self.medium, self.key, lambda t, c: None, lambda m: None,
                                        log=lambda line: None)
        try:
            reception.call(lambda s: s.add_trusted(bytes(16), bytes(64), ("dyzurny-1", "dyzurny-2")))
            reception.deliver(bytes(16), request(text="tajna piwnica"))
            reception.action("dyzurny-1", "logowanie")
            with self.assertRaises(sqlite3.IntegrityError):   # dziennik tylko do dopisywania
                reception.call(lambda s: s.db.execute("DELETE FROM dziennik"))
        finally:
            reception.stop()
        self.assertNotIn("tajna piwnica".encode(), self.files())
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))
        self.assertEqual(durable(self.medium, self.key, "SELECT account, op FROM dziennik"), ("dyzurny-1", "logowanie"))

    @unittest.skipUnless(importlib.util.find_spec("RNS"), "Reticulum")
    def test_preparation_keeps_the_backup_identity_off_the_medium(self):
        import RNS
        work = Path(self.tmp.name)
        args = ["przygotuj", "--nosnik", str(work / "nowy"), "--dyzurni", "2", "--iteracje", str(FAST),
                "--paczka", str(work / "paczka.json"), "--karta", str(work / "karta.json")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(aplikacja.main(args), 0)
        envelopes = json.loads(out.getvalue())["envelopes"]
        self.assertEqual(len(envelopes["paczka-zapasowa"].split()), nosnik.BACKUP_WORDS)
        package = json.loads((work / "paczka.json").read_text())
        backup = nosnik.open_backup(package, envelopes["paczka-zapasowa"])
        on_medium = b"".join(p.read_bytes() for p in (work / "nowy").rglob("*") if p.is_file())
        self.assertNotIn(backup, on_medium)
        card = json.loads((work / "karta.json").read_text())
        self.assertEqual(card["backup"]["key"], RNS.Identity.from_bytes(backup).get_public_key().hex())
        medium = nosnik.Nosnik(work / "nowy")
        main = RNS.Identity.from_bytes(medium.identity(medium.unlock(envelopes["stanowisko"])))
        self.assertEqual(card["main"]["lxmf"], nosnik.lxmf_address(main.get_public_key()).hex())
        self.assertEqual(medium.card(medium.unlock(envelopes["stanowisko"])), card)
        with self.assertRaises(SystemExit):   # paczka na nośniku jest odrzucona
            aplikacja.main(["przygotuj", "--nosnik", str(work / "trzeci"), "--dyzurni", "1",
                            "--paczka", str(work / "trzeci" / "p.json"), "--karta", str(work / "k2.json")])

    def test_wrong_station_password_ends_the_start(self):
        out = io.StringIO()
        with unittest.mock.patch.object(sys, "stdin", io.StringIO("zle haslo\n")), contextlib.redirect_stdout(out):
            code = aplikacja.main(["start", "--nosnik", str(self.root), "--port", "brak"])
        self.assertEqual((code, json.loads(out.getvalue())["event"]), (3, "login_failed"))


class WithCopies(StationTestCase):
    """Przyjecie with copies on a temporary computer disk."""

    def setUp(self):
        self.copies = kopie.Kopie(Path(tempfile.mkdtemp(dir=self.tmp_root())) / "kopie")
        super().setUp()

    def tmp_root(self):
        self.disk = tempfile.TemporaryDirectory()
        self.addCleanup(self.disk.cleanup)
        return self.disk.name

    def open(self):
        return przyjecie.Przyjecie(self.medium, self.key, self.send, lambda m: m.result, clock=lambda: self.now,
                                   log=lambda line: None, random=lambda: 0.5, copies=self.copies)

    def actions(self):
        return [r[0] for r in self.reception.call(lambda s: s.db.execute("SELECT op FROM dziennik ORDER BY id").fetchall())]

    def every_minute(self, minutes):
        for _ in range(minutes):
            self.now += 60
            self.tick()


class CopiesTest(WithCopies):
    """S5: a copy on the computer disk every 5 min, three newest, with the marker only in the copy."""

    def test_copy_every_five_minutes_keeps_three(self):
        self.tick()
        self.assertEqual(len(self.copies.files()), 1)
        self.every_minute(4)
        self.assertEqual(len(self.copies.files()), 1)
        self.every_minute(16)
        self.assertEqual(len(self.copies.files()), kopie.KEEP)
        self.assertEqual(self.copies.newest(self.key), self.now)   # kopie w 0, 5, 10, 15 i 20 min

    def test_copy_has_the_database_identity_and_accounts_and_the_marker_only_there(self):
        self.deliver(self.STATION, request(text="piwnica przy szkole"))
        self.now += kopie.INTERVAL_S
        self.tick()
        path = self.copies.files()[0]
        self.assertNotIn(b"piwnica", path.read_bytes())
        key = kopie.Kopie.unlock(path, self.envelopes["stanowisko"])   # samo hasło stanowiska otwiera kopię
        at, payload = kopie.Kopie.read(path, key)
        self.assertEqual(at, self.now)
        with contextlib.closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(payload["baza"])
            self.assertEqual(db.execute("SELECT count(*) FROM received").fetchone(), (1,))
            self.assertEqual(db.execute("SELECT at FROM kopia").fetchone(), (self.now,))
        self.assertEqual(payload["tozsamosc"], (self.medium.root / "tozsamosc").read_bytes())
        self.assertEqual(payload["konta"], (self.medium.kit.dir / database.ACCOUNTS).read_bytes())
        self.assertIsNone(durable(self.medium, self.key, "SELECT name FROM sqlite_master WHERE name='kopia'"))

    def test_numbered_link_binding_is_in_the_copy_and_restored_medium(self):
        link = {"net_id": 100, "root": 5, "ifac": "ab" * 16, "ttl": 7}
        self.medium.save_link(self.key, link)
        self.now += kopie.INTERVAL_S
        self.tick()
        path = self.copies.files()[0]
        _, payload = kopie.Kopie.read(path, self.key)
        self.assertEqual(payload["wici-link"], (self.medium.root / "wici-link").read_bytes())
        restored = kopie.restore(path, self.key, Path(self.disk.name) / "restored",
                                [("dyzurny-1", self.envelopes["dyzurny-1"]),
                                 ("dyzurny-2", self.envelopes["dyzurny-2"])], self.now)
        self.assertEqual(restored.link(self.key), link)

    def test_failed_copy_is_retried_and_logged_once_without_stopping_reception(self):
        self.tick()   # pierwsza kopia przy starcie; następna za 5 min
        shutil.rmtree(self.copies.dir)
        self.copies.dir.write_text("to nie katalog")   # zapis kopii się nie uda
        self.every_minute(8)
        content = request()
        self.deliver(self.STATION, content)
        self.assertEqual(self.sent[-1][1], received_for(content))
        self.assertEqual(self.actions().count("kopia_nieudana"), 1)
        self.copies.dir.unlink()
        self.every_minute(1)
        self.assertEqual(self.actions()[-1], "kopia_wznowiona")
        self.assertEqual(len(self.copies.files()), 1)

    def test_interrupted_copy_leaves_the_previous_three(self):
        self.every_minute(15)
        before = self.copies.files()
        self.assertEqual(len(before), kopie.KEEP)
        replace = os.replace

        def cut(source, target):   # zanik zasilania przed podmianą pliku kopii (migawki nośnika idą dalej)
            if Path(target).parent == self.copies.dir:
                raise OSError("zanik zasilania")
            return replace(source, target)
        with unittest.mock.patch.object(kopie.os, "replace", side_effect=cut):
            self.every_minute(5)
        self.assertEqual(self.copies.files(), before)
        self.assertTrue(all(kopie.Kopie.read(p, self.key) for p in before))

    def test_new_station_password_rewraps_the_copies(self):
        self.tick()
        new = self.medium.new_station_password(self.key)
        self.copies.rewrap(self.key, self.medium.kit.recovery())
        path = self.copies.files()[0]
        self.assertEqual(kopie.Kopie.unlock(path, new), self.key)
        with self.assertRaises(database.LoginError):
            kopie.Kopie.unlock(path, self.envelopes["stanowisko"])

    def test_copy_on_the_second_medium_and_removal(self):
        self.tick()
        second = kopie.Kopie(Path(self.disk.name) / "drugi-nosnik")
        body = self.reception.call(lambda s: kopie.with_marker(s.db, self.now))
        second.write(self.medium, self.key, body, self.now)
        self.assertEqual(second.newest(self.key), self.now)
        self.assertEqual((self.copies.remove(), second.remove()), ([], []))
        self.assertEqual(self.copies.files() + second.files(), [])


class RecoveryTest(WithCopies):
    """S6: restore from a copy with two duty officers, recovery mode, P = P of the copy + 86 400 s × (1 + n)."""

    def approvers(self):
        return [(n, self.envelopes[n]) for n in ("dyzurny-1", "dyzurny-2")]

    def keep_copy(self):
        """A copy made now, set aside (as if the computer disk kept it while the medium failed)."""
        self.now += kopie.INTERVAL_S
        self.tick()
        aside = Path(self.disk.name) / "zachowane"
        aside.mkdir(exist_ok=True)
        path = self.copies.files()[0]
        return Path(shutil.copy(path, aside / path.name))

    def restored(self, copy, name):
        """Restore copy to a new medium and run the application on it (the previous one stops)."""
        self.reception.stop()
        root = Path(self.tmp.name) / name
        self.medium = kopie.restore(copy, self.key, root, self.approvers(), self.now)
        self.reception = self.open()
        return self.reception

    def status(self, mid, revision, state):
        return self.reception.call(lambda s: self.reception.wysylka.status(s, self.STATION, mid, revision, state, self.now))

    def test_numbered_receiver_card_survives_copy_restore(self):
        card = nosnik.receiver_card(bytes(range(64)), bytes(range(64, 128)), 100, 2, 3)
        self.medium.save_card(self.key, card)
        copy = self.keep_copy()
        restored = self.restored(copy, "numbered")
        self.assertTrue(restored.recovery)
        self.assertEqual(self.medium.card(self.key), card)

    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography for the receiver identity")
    def test_recovered_receiver_requires_staged_fresh_identity_before_sending(self):
        old_private = self.medium.identity(self.key)
        old_public = nosnik.public_identity(old_private)
        backup_public = nosnik.public_identity(bytes(range(64, 128)))
        self.medium.save_card(self.key, nosnik.receiver_card(old_public, backup_public, 100, 2, 3))
        self.medium.save_link(self.key, {"net_id": 100, "root": 1, "ifac": "ab" * 16})
        self.restored(self.keep_copy(), "rekeyed")
        self.reception.finish_recovery("dyzurny-1", 0, True)
        self.reception.stop()
        card_path = Path(self.tmp.name) / "new-receiver-card.json"
        old_card_path = Path(self.tmp.name) / "old-receiver-card.json"
        old_card_path.write_text(json.dumps(self.medium.card(self.key)))
        with self.assertRaises(database.StorageError):
            rekey.activate(self.medium, self.key, self.approvers(), old_card_path)
        with unittest.mock.patch.object(self.medium, "save_card", side_effect=OSError("power cut")):
            with self.assertRaises(OSError):
                rekey.stage(self.medium, self.key, self.approvers(), card_path)
        self.assertEqual(durable(self.medium, self.key, "SELECT blocked FROM env_send_guard WHERE id=1"), (1,))
        card = rekey.stage(self.medium, self.key, self.approvers(), card_path)
        self.assertNotEqual(self.medium.identity(self.key), old_private)
        self.assertEqual(card["main"]["key"], nosnik.public_identity(self.medium.identity(self.key)).hex())
        with self.assertRaises(database.StorageError):   # a card file is never overwritten
            rekey.stage(self.medium, self.key, self.approvers(), card_path)
        self.assertEqual(self.medium.card(self.key), card)
        with self.assertRaises(database.LoginError):   # one officer twice is not two officers
            rekey.activate(self.medium, self.key, [self.approvers()[0]] * 2, card_path)
        self.assertEqual(durable(self.medium, self.key, "SELECT blocked FROM env_send_guard WHERE id=1"), (1,))
        card_path.write_text(json.dumps({**card, "main": {**card["main"], "id": 99}}))
        with self.assertRaises(database.StorageError):
            rekey.activate(self.medium, self.key, self.approvers(), card_path)
        card_path.write_text(json.dumps(card))
        with unittest.mock.patch.object(self.medium, "save", side_effect=OSError("power cut")):
            with self.assertRaises(OSError):
                rekey.activate(self.medium, self.key, self.approvers(), card_path)
        self.assertEqual(durable(self.medium, self.key, "SELECT blocked FROM env_send_guard WHERE id=1"), (1,))
        rekey.activate(self.medium, self.key, self.approvers(), card_path)
        self.assertIsNone(durable(self.medium, self.key, "SELECT blocked FROM env_send_guard WHERE id=1"))
        with self.assertRaises(database.StorageError):
            rekey.activate(self.medium, self.key, self.approvers(), card_path)
        self.reception = self.open()
        self.assertFalse(self.reception.recovery)

    def test_identity_commands_from_the_command_line(self):
        self.reception.stop()
        lines = "\n".join([self.envelopes["stanowisko"]] + [f"{n} {p}" for n, p in self.approvers()]) + "\n"
        for args in (["aktywuj-tozsamosc", "--karta", "karta.json"],      # bez potwierdzenia instalacji kart
                     ["nowa-tozsamosc", "--karta", str(Path(self.tmp.name) / "karta.json")]):   # bez odzyskania
            out = io.StringIO()
            with unittest.mock.patch.object(sys, "stdin", io.StringIO(lines)), contextlib.redirect_stdout(out):
                code = aplikacja.main([args[0], "--nosnik", str(self.medium.root), *args[1:]])
            self.assertEqual((code, json.loads(out.getvalue())["event"]), (3, "identity_failed"))
        self.assertFalse((Path(self.tmp.name) / "karta.json").exists())
        self.reception = self.open()

    def test_copy_at_nine_status_at_ten_spare_computer_at_ten_to_ten(self):
        content = request()
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        copy = self.keep_copy()                    # kopia z 09:00 z przyjętym zgłoszeniem
        start = self.now
        self.now = start + 3600                    # 10:00, STATUS nadany po kopii
        sent_at_ten = self.status(mid, revision, 2)
        self.now = start + 50 * 60                 # komputer zapasowy wskazuje 09:50
        self.restored(copy, "nowy")
        self.assertTrue(self.reception.recovery)
        p = self.reception.finish_recovery("dyzurny-1", 0, True)
        self.assertEqual(p, wysylka.RECOVERY_S)
        self.assertGreater(self.status(mid, revision, 3), sent_at_ten)

    def test_two_recoveries_from_the_same_copy(self):
        content = request()
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        copy = self.keep_copy()
        self.now += 600
        self.restored(copy, "pierwszy")
        self.reception.finish_recovery("dyzurny-1", 0, True)
        self.now += 300
        after_first = self.status(mid, revision, 2)
        self.now -= 3600                           # drugi komputer ma zegar o godzinę do tyłu
        self.restored(copy, "drugi")
        self.assertEqual(self.reception.finish_recovery("dyzurny-2", 1, True), 2 * wysylka.RECOVERY_S)
        self.assertGreater(self.status(mid, revision, 3), after_first)

    def test_restart_after_recovery_is_not_blocked(self):
        content = request()
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        self.restored(self.keep_copy(), "nowy")
        self.reception.finish_recovery("dyzurny-1", 0, True)
        self.status(mid, revision, 2)              # numer odpowiada czasowi o dobę późniejszemu
        self.now += 60
        self.restart()
        self.assertFalse(self.reception.recovery)

    def test_no_sending_until_the_recovery_ends_then_a_new_copy_first(self):
        copy = self.keep_copy()
        self.restored(copy, "nowy")
        self.copies.remove()
        self.sent.clear()
        content = request()
        self.deliver(self.STATION, content)
        self.now += 900
        self.tick()
        self.assertEqual((self.sent, self.copies.files()), ([], []))
        with self.assertRaises(ValueError):
            self.reception.finish_recovery("dyzurny-1", 0, False)   # bez potwierdzenia zegara
        self.reception.finish_recovery("dyzurny-1", 0, True)
        self.assertEqual(self.sent[0][1], received_for(content))
        _, payload = kopie.Kopie.read(self.copies.files()[0], self.key)
        with contextlib.closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(payload["baza"])
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='p'").fetchone(), (wysylka.RECOVERY_S,))
        self.assertEqual(self.actions()[-2:], ["odtworzenie", "odzyskanie_koniec"])
        self.assertIsNone(durable(self.medium, self.key, "SELECT name FROM sqlite_master WHERE name='kopia'"))
        self.assertEqual(durable(self.medium, self.key, "SELECT blocked FROM env_send_guard WHERE id=1"), (1,))

    def test_restore_needs_two_different_officers_and_an_empty_medium(self):
        self.tick()
        copy = self.copies.files()[0]
        root = Path(self.tmp.name) / "nowy"
        for approvers in ([("dyzurny-1", self.envelopes["dyzurny-1"])] * 2,
                          [("dyzurny-1", self.envelopes["dyzurny-1"]), ("dyzurny-2", "zle haslo")]):
            with self.assertRaises(database.LoginError):
                kopie.restore(copy, self.key, root, approvers, self.now)
            self.assertFalse(nosnik.Nosnik(root).exists())
        with self.assertRaises(database.StorageError):
            kopie.restore(copy, self.key, self.medium.root, self.approvers(), self.now)

    def test_restore_from_the_command_line(self):
        self.tick()
        state = Path(self.disk.name) / "stan"
        lines = "\n".join([self.envelopes["stanowisko"]] + [f"{n} {p}" for n, p in self.approvers()]) + "\n"
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"WICI_STATE": str(state)}), \
                unittest.mock.patch.object(sys, "stdin", io.StringIO(lines)), contextlib.redirect_stdout(out):
            code = aplikacja.main(["odtworz", "--nosnik", str(Path(self.tmp.name) / "nowy"),
                                   "--kopie", str(self.copies.dir)])
        self.assertEqual((code, json.loads(out.getvalue())["event"]), (0, "restored"))
        medium = nosnik.Nosnik(Path(self.tmp.name) / "nowy")
        self.assertEqual(medium.unlock(self.envelopes["stanowisko"]), self.key)
        self.assertEqual(medium.identity(self.key), self.medium.identity(self.key))



class OnlineLink:
    """A WICI-Link bearer for send_wici that keeps the frames it was given."""

    network = 100

    def status(self, now):
        return {"online": True, "room": True}

    def send_frames(self, frames):
        return frames


@unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography for the receiver identity")
class BackupActivationTest(unittest.TestCase):
    """The backup identity package yields one lineage that seals envelopes; every other activation is guarded."""

    PASSWORD = "paczka zapasowa szesc slow testu"

    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric import x25519
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.backup = secrets.token_bytes(64)
        backup_public = nosnik.public_identity(self.backup)
        self.card = nosnik.receiver_card(nosnik.public_identity(secrets.token_bytes(64)), backup_public, 100, 2, 3)
        self.package = self.dir / "paczka.json"
        self.package.write_text(json.dumps(nosnik.backup_package(self.backup, backup_public, self.PASSWORD, FAST)))
        self.link = {"net_id": 100, "root": 1, "ifac": "ab" * 16}
        station_private = x25519.X25519PrivateKey.generate()
        self.station_key = station_private.public_key().public_bytes_raw() + secrets.token_bytes(32)
        self.now = 1_800_000_000.0

    def activate(self, name):
        return rekey.activate_backup(self.package, self.PASSWORD, self.dir / name, 2, self.card, self.link, FAST)

    def run_station(self, medium, key, sends=1, finish=None):
        """Open the application on medium, register station 4, and send; the envelope counters (None: refused)."""
        reception = przyjecie.Przyjecie(medium, key, lambda *_: None, lambda m: None, clock=lambda: self.now,
                                        log=lambda line: None, random=lambda: 0.5)
        try:
            if finish:
                finish(reception)
            source = nosnik.lxmf_address(self.station_key)

            def register(store):
                if store.db.execute("SELECT 1 FROM numery WHERE station=4").fetchone() is None:
                    store.add_trusted(source, self.station_key, ("dyzurny-1", "dyzurny-2"))
                    store.db.execute("INSERT INTO numery VALUES(?,?,?,?)", (100, 4, source, self.station_key))
            reception.call(register)
            content = received_for(request())
            frames = [reception.call(lambda s: reception.send_wici(OnlineLink(), source, content))
                      for _ in range(sends)]
            return [None if f is None else int.from_bytes(f[0][5:9], "big") for f in frames]
        finally:
            reception.stop()

    def test_second_activation_is_guarded_until_a_new_identity(self):
        first, key, envelopes, guarded = self.activate("pierwszy")
        self.assertFalse(guarded)
        self.assertEqual(first.identity(key), self.backup)
        self.assertIn(rekey.USED, json.loads(self.package.read_text()))
        self.assertEqual(self.run_station(first, key, 2), [0, 1])
        self.assertEqual(durable(first, key, "SELECT op, account FROM dziennik ORDER BY id"), ("aktywacja_zapasowej", ""))

        second, key2, envelopes2, guarded = self.activate("drugi")   # e.g. the first medium was lost
        self.assertTrue(guarded)
        self.assertEqual(self.run_station(second, key2), [None])
        self.assertIsNone(durable(second, key2, "SELECT 1 FROM sqlite_master WHERE name='env_send'"))
        approvers = [(n, envelopes2[n]) for n in ("dyzurny-1", "dyzurny-2")]
        card_path = self.dir / "nowa-karta.json"
        card = rekey.stage(second, key2, approvers, card_path)
        self.assertEqual(card["backup"], self.card["backup"])
        rekey.activate(second, key2, approvers, card_path)
        self.assertNotEqual(second.identity(key2), self.backup)
        self.assertEqual(self.run_station(second, key2), [0])   # a fresh identity, so a fresh key

        third, key3, _, guarded = self.activate("trzeci")   # the used backup stays used
        self.assertTrue(guarded)
        self.assertEqual(self.run_station(third, key3), [None])

    def test_restored_backup_medium_is_guarded(self):
        medium, key, envelopes, _ = self.activate("pierwszy")
        self.assertEqual(self.run_station(medium, key), [0])
        copies = kopie.Kopie(self.dir / "kopie")
        with contextlib.closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(medium.load(key))
            copies.write(medium, key, kopie.with_marker(db, self.now), self.now)
        self.assertEqual(self.run_station(medium, key), [64])   # sent after the copy
        approvers = [(n, envelopes[n]) for n in ("dyzurny-1", "dyzurny-2")]
        restored = kopie.restore(copies.files()[0], key, self.dir / "odtworzony", approvers, self.now)
        self.assertEqual(restored.identity(key), self.backup)
        self.assertEqual(self.run_station(restored, key, finish=lambda r: r.finish_recovery("dyzurny-1", 0, True)),
                         [None])

    def test_interrupted_activation_never_yields_a_second_unguarded_medium(self):
        replace = os.replace

        def cut(source, target):   # power loss before the package is marked
            if Path(target) == self.package:
                raise OSError("zanik zasilania")
            return replace(source, target)
        with unittest.mock.patch.object(rekey.os, "replace", side_effect=cut), self.assertRaises(OSError):
            self.activate("przerwany-paczka")
        self.assertNotIn(rekey.USED, json.loads(self.package.read_text()))
        self.assertFalse(nosnik.Nosnik(self.dir / "przerwany-paczka").exists())

        with unittest.mock.patch.object(nosnik.Nosnik, "save_identity", side_effect=OSError("zanik zasilania")), \
                self.assertRaises(OSError):
            self.activate("przerwany-nosnik")
        self.assertIn(rekey.USED, json.loads(self.package.read_text()))
        partial = nosnik.Nosnik(self.dir / "przerwany-nosnik")
        with self.assertRaises(database.StorageError):   # an interrupted medium is not prepared again ...
            self.activate("przerwany-nosnik")
        self.assertTrue(partial.exists())
        self.assertFalse((partial.root / "tozsamosc").exists())   # ... and does not start
        medium, key, _, guarded = self.activate("ponowiony")
        self.assertTrue(guarded)
        self.assertEqual(self.run_station(medium, key), [None])

    def test_wrong_password_or_card_leaves_the_package_unused(self):
        before = self.package.read_bytes()
        with self.assertRaises(database.LoginError):
            rekey.activate_backup(self.package, "zle haslo", self.dir / "a", 2, self.card, self.link, FAST)
        other = {**self.card, "backup": self.card["main"]}
        for card, link in ((other, self.link), (self.card, None), (self.card, {**self.link, "root": 3}),
                           (self.card, {**self.link, "net_id": 101})):
            with self.assertRaises(database.StorageError):
                rekey.activate_backup(self.package, self.PASSWORD, self.dir / "a", 2, card, link, FAST)
        self.assertEqual(self.package.read_bytes(), before)
        self.assertFalse(nosnik.Nosnik(self.dir / "a").exists())

    def test_activation_from_the_command_line(self):
        card_path = self.dir / "karta.json"
        card_path.write_text(json.dumps(self.card))
        events = []
        for name in ("pierwszy", "drugi"):
            out = io.StringIO()
            with unittest.mock.patch.object(sys, "stdin", io.StringIO(self.PASSWORD + "\n")), \
                    contextlib.redirect_stdout(out):
                code = aplikacja.main(["aktywuj-zapasowa", "--nosnik", str(self.dir / name), "--dyzurni", "2",
                                       "--paczka", str(self.package), "--karta", str(card_path), "--root-id", "1",
                                       "--ifac", "ab" * 16, "--iteracje", str(FAST)])
            event = json.loads(out.getvalue())
            events.append((code, event["event"], event["guarded"], sorted(event["envelopes"])))
        self.assertEqual(events, [(0, "envelopes", False, ["dyzurny-1", "dyzurny-2", "stanowisko"]),
                                  (0, "envelopes", True, ["dyzurny-1", "dyzurny-2", "stanowisko"])])


class FakeStack:
    def __init__(self):
        self.announced = 0

    def announce(self):
        self.announced += 1

    def stop(self):
        self.stopped = True

    def status(self, now):
        return {"online": True, "since_rx": 5.0, "dropped": {"bad_signature": 0, "pending_full": 0}}


def station_card(key):
    """Station card as `card` over USB returns it (usb-protocol.md)."""
    return {"name": panel.station_name(key), "lxmf": nosnik.lxmf_address(key).hex(), "key": key.hex(),
            "address": ["ul. Długa 5, wejście od podwórza"], "fingerprint": panel.fingerprint(key)}


class PanelTest(StationTestCase):
    """S7: duty officer operations: login and 5 min lock, decisions with their rules, TEST, quarantine,
    trusted list with two officers, node, handover, passwords; and the HTTP side."""

    def setUp(self):
        super().setUp()
        self.mono = 1000.0
        self.stack = FakeStack()
        self.d = panel.Dyzur(self.reception, self.medium, self.key, self.stack, clock=lambda: self.now,
                             monotonic=lambda: self.mono)
        self.d.login("dyzurny-1", self.envelopes["dyzurny-1"])

    def report(self, **fields):
        content = request(**fields)
        self.deliver(self.STATION, content)
        mid, revision = wzorzec.decode_message(content)[2:4]
        return {"source": self.STATION.hex(), "id": mid, "revision": revision}

    def log(self):
        return [(e["account"], e["op"]) for e in reversed(self.d.view()["log"])]

    def test_rejected_envelopes_raise_the_panel_alarm(self):
        # Dane z przyjecie.envelope_alarm (test_stanowisko_wici); tu tylko to, że panel je pokazuje i przekazuje zmianie.
        self.assertFalse(self.d.view()["envelopes"]["active"])
        frame = lambda sender, rest: bytes([0]) + sender.to_bytes(2, "big") + rest
        self.reception.call(lambda s: self.reception._count_unauthenticated(100, frame(9, bytes(20)), "unknown station number", 0))
        self.reception.call(lambda s: self.reception._set_aside(100, frame(4, bytes(30)), "counter outside replay window", 0))
        view = self.d.view()
        e = view["envelopes"]
        self.assertTrue(e["active"] and view["handover"]["envelope_alarm"])
        self.assertEqual((e["total"], e["rows"][0]["sender"], e["unauthenticated"]["unknown station number"]["sender"]), (1, 4, 9))
        self.assertEqual(e["stations"], {})   # bez numerowanej karty stacji numer zostaje numerem
        def numbered(store):   # stacja z kartą i numerem 4 w sieci 100
            with store.db:
                store.db.execute("INSERT INTO karty VALUES(?, 'WICI-N4', '[]', '')", (bytes([7]) * 16,))
                store.db.execute("INSERT INTO numery VALUES(100, 4, ?, ?)", (bytes([7]) * 16, bytes(32)))
        self.reception.call(numbered)
        self.assertEqual(self.d.view()["envelopes"]["stations"], {"100:4": "WICI-N4"})

    def test_report_received_while_the_panel_is_idle_raises_the_version(self):
        # Bez żadnego POST z panelu: wersja rośnie, bo zmieniły się dane, więc otwarty panel rysuje zgłoszenie.
        web = panel.Panel(self.d)
        first = web.queue(-1)
        self.assertEqual(web.queue(-1)["v"], first["v"])   # te same dane, ta sama wersja
        self.report()
        after = web.queue(-1)
        self.assertGreater(after["v"], first["v"])
        self.assertEqual(len(after["reports"]), len(first["reports"]) + 1)
        self.now += 30   # same liczniki sekund nie podnoszą wersji
        self.assertEqual(web.queue(-1)["v"], after["v"])

    def test_operator_can_override_only_a_trusted_station_reply_bearer(self):
        class Link(FakeStack):
            address = bytes(16)
            network = 100

        self.d.stos = bearers.Bearers({"wici": Link(), "reticulum": Link()}, "wici")
        self.d.bearer({"source": self.STATION.hex(), "bearer": "reticulum"})
        self.assertEqual(durable(self.medium, self.key, "SELECT bearer FROM bearer_override WHERE source=?",
                                 (self.STATION,)), ("reticulum",))
        self.restart()
        self.d.p = self.reception
        self.assertEqual(self.reception.call(lambda s: self.reception.bearer_override.get(self.STATION)), "reticulum")
        with self.assertRaises(ValueError):
            self.d.bearer({"source": self.STATION.hex(), "bearer": "wici"})
        with self.assertRaises(ValueError):
            self.d.bearer({"source": self.OTHER.hex(), "bearer": "reticulum"})
        self.d.bearer({"source": self.STATION.hex(), "bearer": "auto"})
        self.assertIsNone(durable(self.medium, self.key, "SELECT bearer FROM bearer_override WHERE source=?",
                                  (self.STATION,)))
        self.assertIn(("dyzurny-1", "nosnik_odpowiedzi"), self.log())

    def test_login_and_lock_after_five_minutes(self):
        self.d.logout()
        with self.assertRaises(database.LoginError):
            self.d.login("dyzurny-1", self.envelopes["dyzurny-2"])
        with self.assertRaises(panel.NotLoggedIn):
            self.d.status({**self.report(), "state": 2})
        self.d.login("dyzurny-2", self.envelopes["dyzurny-2"])
        self.mono += panel.LOCK_S - 1
        self.d.touch()
        self.mono += panel.LOCK_S - 1
        self.d.current()                                   # aktywność przesuwa blokadę
        self.mono += panel.LOCK_S + 1
        with self.assertRaises(panel.NotLoggedIn):
            self.d.current()
        self.assertIn(("dyzurny-2", "blokada_5_min"), self.log())

    def test_reports_sorted_by_urgency_then_time_tests_apart(self):
        first = self.report(kind=0, text="")
        self.now += 10
        urgent = self.report(kind=0)
        test = self.report(kind=5, people=1, text="test")
        self.reception.call(lambda s: s.db.execute("UPDATE received SET payload=? WHERE id=?", (
            wzorzec.encode_message([1, 0, urgent["id"], 1, 0, 2, "ul. Krótka 1", "duszności", 2]), urgent["id"])) and s.db.commit())
        view = self.d.view()
        self.assertEqual([r["id"] for r in view["reports"]], [urgent["id"], first["id"]])
        self.assertEqual([t["id"] for t in view["tests"]], [test["id"]])
        self.assertEqual(view["reports"][0]["number"], panel.short_number(urgent["id"]))

    def test_read_and_decisions_follow_their_rules(self):
        r = self.report()
        self.d.status({**r, "state": 2})
        self.tick()
        self.assertEqual(wzorzec.decode_message(self.sent[-1][1])[5], 2)
        with self.assertRaises(ValueError):
            self.d.status({**r, "state": 3, "podmiot": "PSP Gdańsk"})        # bez funkcji, kanału i czasu
        with self.assertRaises(ValueError):
            self.d.status({**r, "state": 5})                                 # bez REPLY
        self.d.status({**r, "state": 4, "adresat": "ZRM", "czas": "10:15"})
        self.d.status({**r, "state": 3, "podmiot": "PSP Gdańsk", "funkcja": "dyżurny", "kanal": "telefon", "czas": "10:20"})
        self.d.status({**r, "state": 5, "reply": "Proszę czekać przy wejściu od podwórza"})
        self.tick()
        kinds = [wzorzec.decode_message(c)[1] for _, c in self.sent]
        self.assertEqual(kinds.count(wysylka.REPLY), 1)
        item = self.d.view()["reports"][0]
        self.assertEqual((item["state"], item["reply"]), (5, True))
        self.assertEqual([d["state"] for d in item["decisions"]], [4, 3])
        self.assertEqual(item["decisions"][1]["detail"]["kanal"], "telefon")
        self.assertIn(("dyzurny-1", "stan_3"), self.log())

    def test_tests_confirmed_together(self):
        items = [self.report(kind=5, people=1, text="test") for _ in range(3)]
        self.d.read_tests({"items": items[:2]})
        self.assertEqual([t["state"] for t in self.d.view()["tests"]].count(2), 2)

    def test_quarantine_approve_one_message_and_reject(self):
        approved, rejected = request(), request()
        for content in (approved, rejected):
            self.deliver(self.OTHER, content)
        a, b = (wzorzec.decode_message(c)[2:4] for c in (approved, rejected))
        self.d.quarantine({"source": self.OTHER.hex(), "id": a[0], "revision": a[1], "decision": "approve"})
        self.tick()
        self.assertEqual(self.sent[-1], (self.OTHER, received_for(approved)))
        self.d.quarantine({"source": self.OTHER.hex(), "id": b[0], "revision": b[1], "decision": "reject"})
        view = self.d.view()
        self.assertEqual((len(view["quarantine"]), len(view["reports"])), (0, 1))
        self.assertNotIn(self.OTHER.hex(), [t["source"] for t in view["trusted"]])   # nadawca nie jest zaufany

    def test_trust_needs_the_fingerprint_and_a_second_officer(self):
        key = os.urandom(64)
        card = station_card(key)
        second = {"account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]}
        with self.assertRaises(ValueError):
            self.d.trust({"card": card, "fingerprint": "0000 0000 0000 0000", **second})
        with self.assertRaises(database.LoginError):
            self.d.trust({"card": card, "fingerprint": card["fingerprint"], "account2": "dyzurny-1",
                          "password2": self.envelopes["dyzurny-1"]})
        with self.assertRaises(ValueError):
            self.d.trust({"card": {**card, "lxmf": "00" * 16}, "fingerprint": card["fingerprint"], **second})
        self.assertEqual(self.d.trust({"card": card, "fingerprint": card["fingerprint"].upper(), **second})["name"], card["name"])
        trusted = {t["source"]: t for t in self.d.view()["trusted"]}
        self.assertEqual(trusted[card["lxmf"]]["station"], card["name"])
        self.d.untrust({"source": card["lxmf"]})
        self.deliver(bytes.fromhex(card["lxmf"]), request())
        view = self.d.view()
        self.assertEqual(view["removed"], [{"source": card["lxmf"], "station": card["name"], "messages": 1}])

    def trusted_cards(self):
        return [t["source"] for t in self.d.view()["trusted"] if t["source"] != self.STATION.hex()]

    def numbers(self):
        return self.reception.call(lambda s: s.db.execute(
            "SELECT net_id, station, hex(source) FROM numery ORDER BY net_id, station").fetchall())

    def test_station_number_moves_to_a_new_key_only_on_explicit_rebind(self):
        second = {"account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]}
        first = station_card(os.urandom(64))
        first.update(net_id=100, id=4, x25519=first["key"][:64])
        self.d.trust({"card": first, "fingerprint": first["fingerprint"], **second})
        old = bytes.fromhex(first["lxmf"])
        self.reception.call(lambda s: s.db.execute("INSERT INTO bearer_override VALUES(?, 'wici')", (old,)))
        self.reception.bearer_override[old] = "wici"
        other = station_card(os.urandom(64))
        other.update(net_id=100, id=4, x25519=other["key"][:64])
        ask = {"card": other, "fingerprint": other["fingerprint"], **second}
        before = (self.numbers(), self.log())
        # Number held by another key: nothing changes, the panel gets what the rebind would undo.
        replace = self.d.trust(ask)["replace"]
        self.assertEqual(replace, {"net_id": 100, "station": 4, "renumbered_from": None,
                                   "old": {"name": first["name"], "fingerprint": first["fingerprint"]}})
        self.assertEqual((self.numbers(), self.log()), before)
        with self.assertRaisesRegex(ValueError, "zmieniło się"):   # confirmed for another binding
            self.d.trust({**ask, "replace": dict(replace, station=5)})
        with self.assertRaises(database.LoginError):   # the rebind needs the second officer too
            self.d.trust({**ask, "replace": replace, "account2": "dyzurny-1", "password2": self.envelopes["dyzurny-1"]})
        self.assertEqual(self.numbers(), before[0])
        self.assertEqual(self.d.trust({**ask, "replace": replace})["name"], other["name"])
        self.assertEqual(self.numbers(), [(100, 4, other["lxmf"].upper())])
        view = self.d.view()
        self.assertEqual(self.trusted_cards(), [other["lxmf"]])
        self.assertNotIn(old, self.reception.bearer_override)
        self.assertEqual(self.reception.call(lambda s: s.db.execute(
            "SELECT count(*) FROM bearer_override WHERE source=?", (old,)).fetchone()), (0,))
        self.assertEqual(self.log()[-3:], [("dyzurny-1", "zaufana_usunieta"), ("dyzurny-1", "numer_przepiety"),
                                           ("dyzurny-1", "zaufana_dodana")])
        entry = json.loads(next(e["detail"] for e in view["log"] if e["op"] == "numer_przepiety"))
        self.assertEqual((entry["old"]["fingerprint"], entry["fingerprint"], entry["zgoda"]),
                         (first["fingerprint"], other["fingerprint"], ["dyzurny-1", "dyzurny-2"]))
        self.deliver(old, request())   # the old key is a removed station: quarantine and the takeover alarm
        self.assertEqual(self.d.view()["removed"][0]["messages"], 1)
        # The same key under another number: its old number is freed, again only after confirmation.
        renumber = {**ask, "card": dict(other, id=5)}
        replace = self.d.trust(renumber)["replace"]
        self.assertEqual(replace, {"net_id": 100, "station": 5, "old": None, "renumbered_from": 4})
        self.d.trust({**renumber, "replace": replace})
        self.assertEqual(self.numbers(), [(100, 5, other["lxmf"].upper())])
        # A number left by an untrusted key also moves only on rebind; no trust to remove then.
        self.d.untrust({"source": other["lxmf"]})
        third = station_card(os.urandom(64))
        third.update(net_id=100, id=5, x25519=third["key"][:64])
        ask = {"card": third, "fingerprint": third["fingerprint"], **second}
        replace = self.d.trust(ask)["replace"]
        self.d.trust({**ask, "replace": replace})
        self.assertEqual(self.numbers(), [(100, 5, third["lxmf"].upper())])
        self.assertEqual(self.log()[-2:], [("dyzurny-1", "numer_przepiety"), ("dyzurny-1", "zaufana_dodana")])
        with self.assertRaisesRegex(ValueError, "klucz koperty"):
            self.d.trust({"card": dict(third, id=6, x25519="00" * 32), "fingerprint": third["fingerprint"], **second})

    def test_messages_held_for_a_removed_station_are_shown_apart(self):
        r = self.report()
        self.d.untrust({"source": r["source"]})
        self.reception.call(lambda s: self.reception.wysylka.status(s, self.STATION, r["id"], r["revision"], 2, self.now))
        view = self.d.view()
        self.assertEqual((view["node"]["waiting"], view["node"]["held"], view["node"]["oldest_s"]), (0, 1, None))
        self.assertEqual((view["handover"]["unsent"], view["handover"]["held"]), (0, 1))

    def test_rebind_rolls_back_as_a_whole(self):
        second = {"account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]}
        first, other = station_card(os.urandom(64)), station_card(os.urandom(64))
        for c in (first, other):
            c.update(net_id=100, id=4, x25519=c["key"][:64])
        self.d.trust({"card": first, "fingerprint": first["fingerprint"], **second})
        ask = {"card": other, "fingerprint": other["fingerprint"], **second}
        replace = self.d.trust(ask)["replace"]
        self.reception.call(lambda store: store.db.execute(
            "CREATE TRIGGER refuse_number BEFORE INSERT ON numery BEGIN SELECT RAISE(ABORT, 'fault'); END"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.trust({**ask, "replace": replace})
        self.assertEqual(self.numbers(), [(100, 4, first["lxmf"].upper())])
        self.assertEqual(self.trusted_cards(), [first["lxmf"]])

    def test_numbered_card_and_trust_roll_back_together(self):
        card = station_card(os.urandom(64))
        card.update(net_id=100, id=4, x25519=card["key"][:64])
        self.reception.call(lambda store: store.db.execute(
            "CREATE TRIGGER refuse_number BEFORE INSERT ON numery BEGIN SELECT RAISE(ABORT, 'fault'); END"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.trust({"card": card, "fingerprint": card["fingerprint"],
                          "account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]})
        self.assertEqual(self.reception.call(lambda store: store.db.execute(
            "SELECT count(*) FROM trusted WHERE source=?", (bytes.fromhex(card["lxmf"]),)).fetchone()), (0,))

    def test_node_handover_backup_and_announce(self):
        self.report()
        self.d.announce({})
        self.assertEqual(self.stack.announced, 1)
        view = self.d.view()
        self.assertEqual((view["node"]["online"], view["handover"]["open"]), (True, 1))
        second = Path(self.tmp.name) / "drugi"
        second.mkdir()
        self.d.handover({"path": str(second)})
        self.assertEqual(len(kopie.Kopie(second / "wici-kopie").files()), 1)
        self.assertIsNone(self.d.user)
        self.assertEqual(self.log()[-2:], [("dyzurny-1", "przekazanie_zmiany"), ("dyzurny-1", "wylogowanie")])

    def test_new_passwords(self):
        own = self.d.new_password({"account": "dyzurny-1"})["password"]   # własne konto: jedna osoba
        self.medium.login("dyzurny-1", own, self.key)
        for account in ("dyzurny-2", "stanowisko"):   # cudze hasło dałoby jednej osobie „zgodę drugiego”
            with self.assertRaises(ValueError):
                self.d.new_password({"account": account})
        second = {"account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]}
        new = self.d.new_password({"account": "dyzurny-2", **second})["password"]
        self.medium.login("dyzurny-2", new, self.key)
        result = self.d.new_password({"account": "stanowisko", "account2": "dyzurny-2", "password2": new})
        self.assertEqual((nosnik.Nosnik(self.medium.root).unlock(result["password"]), result["copies_failed"]),
                         (self.key, None))
        self.assertIn(("dyzurny-1", "nowe_haslo"), self.log())

    def test_http_panel_needs_the_ticket_cookie_and_loopback(self):
        import http.client
        web = panel.Panel(self.d)
        server = panel.serve(web, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            def request_(method, path, body=None, headers=None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                c.request(method, path, body, {"Host": f"127.0.0.1:{port}", **(headers or {})})
                r = c.getresponse()
                data = r.read()
                c.close()
                return r.status, r.getheader("Set-Cookie"), data
            self.assertEqual(request_("GET", "/health")[0], 200)
            self.assertEqual(request_("GET", "/api/operator/queue")[0], 403)
            self.assertEqual(request_("GET", "/start?t=zly")[0], 403)
            ticket = web.ticket()
            status, cookie, _ = request_("GET", f"/start?t={ticket}")
            self.assertEqual(status, 303)
            self.assertEqual(request_("GET", f"/start?t={ticket}")[0], 403)   # odnośnik działa raz
            auth = {"Cookie": cookie.split(";")[0]}
            for path in ("/", "/app.js", "/app.css", "/ui/app.css", "/ui/logo.svg", "/ui/logo-dark.svg", "/ui/dialog.js"):   # wygląd wspólny z wici/ui
                self.assertEqual(request_("GET", path, headers=auth)[0], 200, path)
            status, _, data = request_("GET", "/api/operator/queue", headers=auth)
            self.assertEqual((status, json.loads(data)["user"], json.loads(data)["sound"]), (200, "dyzurny-1", True))
            web.sound = False   # start --bez-dzwieku: panel dostaje to w każdej odpowiedzi
            self.assertFalse(json.loads(request_("GET", "/api/operator/queue", headers=auth)[2])["sound"])
            json_post = {**auth, "Content-Type": "application/json"}
            status, _, data = request_("POST", "/api/operator/login",
                                       json.dumps({"account": "dyzurny-2", "password": "zle"}), json_post)
            self.assertEqual(status, 401)
            self.assertEqual(request_("POST", "/api/operator/announce", "{}", {**json_post, "Origin": "http://zly.example"})[0], 403)
            self.assertEqual(request_("POST", "/api/operator/announce", "{}", json_post)[0], 200)
            self.assertEqual(request_("GET", "/", headers=auth)[0], 200)
        finally:
            server.shutdown()
            server.server_close()


class AnnounceBulletinTest(StationTestCase):
    """S8: announce every 6 h ±20% and after a reconnection; BULLETIN to each trusted station with progress."""

    def setUp(self):
        self.announced, self.online = 0, True
        super().setUp()

    def open(self):
        return przyjecie.Przyjecie(self.medium, self.key, self.send, lambda m: m.result, clock=lambda: self.now,
                                   log=lambda line: None, random=lambda: 0.5, announce=self.announce,
                                   online=lambda: self.online)

    def announce(self):
        self.announced += 1

    def test_every_six_hours_and_after_a_reconnection(self):
        self.tick()
        self.assertEqual(self.announced, 0)                    # po starcie ogłasza sam stos
        self.now += przyjecie.Przyjecie.ANNOUNCE_S - 60
        self.tick()
        self.assertEqual(self.announced, 0)
        self.now += 60
        self.tick()
        self.assertEqual(self.announced, 1)
        self.online = False
        self.tick()
        self.online = True
        self.tick()
        self.assertEqual(self.announced, 2)                    # stacja wróciła

    def test_six_hours_have_twenty_percent_jitter(self):
        self.reception.stop()
        for r, low in ((0.0, 0.8), (0.999999, 1.2)):
            reception = przyjecie.Przyjecie(self.medium, self.key, self.send, lambda m: True, clock=lambda: self.now,
                                            log=lambda line: None, random=lambda: r, announce=self.announce)
            reception.call(lambda s: reception.tick())
            self.assertAlmostEqual(reception.next_announce - self.now, przyjecie.Przyjecie.ANNOUNCE_S * low, delta=1)
            reception.stop()
        self.reception = self.open()

    def test_bulletin_to_every_station_with_progress(self):
        stations = [bytes([i]) * 16 for i in range(1, 4)]
        for st in stations:
            self.reception.call(lambda s, st=st: s.add_trusted(st, st * 4, ("dyzurny-1", "dyzurny-2")))
        d = panel.Dyzur(self.reception, self.medium, self.key, FakeStack(), clock=lambda: self.now)
        d.login("dyzurny-1", self.envelopes["dyzurny-1"])
        content = request()
        self.result = None
        self.reception.deliver(self.STATION, content)          # RECEIVED czeka w drodze
        mid = d.bulletin({"text": "Woda pitna: beczkowóz przy szkole od 14:00"})["id"]
        self.tick()
        self.assertEqual(self.kinds()[0], wysylka.RECEIVED)    # RECEIVED przed komunikatem
        self.assertEqual(len({t for t, c in self.sent if wzorzec.decode_message(c)[1] == wysylka.BULLETIN}), 3)
        for message, _ in list(self.reception.wysylka.flight.values()):
            message.result = True
        self.result = True
        self.tick()
        self.tick()
        progress = d.view()["bulletins"][0]
        self.assertEqual((progress["id"], progress["total"], progress["done"]), (mid, 4, 4))   # 3 nowe i STATION
        self.assertIn("Woda pitna", progress["text"])

    def test_sending_bookkeeping_does_not_force_a_snapshot(self):
        saves = []
        real = self.medium.save
        self.medium.save = lambda *args: (saves.append(1), real(*args))
        self.deliver(self.STATION, request())                  # przyjęcie: dziennik przyjęć przed RECEIVED
        before = len(saves)
        self.tick()                                            # DELIVERED: tylko ewidencja
        self.tick()
        self.assertEqual(len(saves), before)
        self.reception.action("dyzurny-1", "logowanie")        # następna zmiana zapisuje też ewidencję
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM outbox WHERE done=0"), (0,))



class ClosingTest(WithCopies):
    """S9: register export, ZAMKNIJ ZDARZENIE with the archive, removal of copies and ZNISZCZ DANE."""

    def setUp(self):
        super().setUp()
        self.quit = []
        self.d = panel.Dyzur(self.reception, self.medium, self.key, FakeStack(), clock=lambda: self.now)
        self.d.on_quit = lambda: self.quit.append(1)
        self.d.login("dyzurny-1", self.envelopes["dyzurny-1"])
        self.content = request(text="piwnica przy szkole")
        self.deliver(self.STATION, self.content)
        mid, revision = wzorzec.decode_message(self.content)[2:4]
        self.mid = mid
        key = {"source": self.STATION.hex(), "id": mid, "revision": revision}
        self.d.status({**key, "state": 3, "podmiot": "PSP Gdańsk", "funkcja": "dyżurny", "kanal": "telefon", "czas": "10:20"})
        self.d.status({**key, "state": 5, "reply": "Proszę czekać przy wejściu"})
        self.d.bulletin({"text": "Woda pitna przy szkole"})
        self.tick()

    def rows(self, data):
        import csv
        return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))

    def test_export_writes_the_register_on_the_medium(self):
        path = Path(self.d.export({})["file"])
        self.assertEqual(path.parent, self.medium.root / zamkniecie.EXPORT)
        data = path.read_bytes()
        rows = self.rows(data)
        self.assertEqual(tuple(rows[0]), zamkniecie.COLUMNS)
        kinds = [r["rodzaj"] for r in rows]
        self.assertEqual(kinds[0], "odbior")
        self.assertIn("stan_3", kinds)
        reception = rows[0]
        self.assertEqual((reception["numer"], reception["tresc"]), (panel.short_number(self.mid), "piwnica przy szkole"))
        decision = next(r for r in rows if r["rodzaj"] == "stan_3")
        self.assertEqual((decision["stan"], decision["potwierdzil"], decision["kanal"], decision["dyzurny"]),
                         ("3", "PSP Gdańsk, dyżurny", "telefon", "dyzurny-1"))
        self.assertEqual(next(r for r in rows if r["rodzaj"] == "komunikat")["tresc"], "Woda pitna przy szkole")
        self.assertNotIn("logowanie", kinds)                    # logowania tylko w dzienniku
        for secret in (self.STATION.hex(), self.KEY.hex(), self.key.hex()):
            self.assertNotIn(secret, data.decode())
        self.assertNotEqual(self.d.export({})["file"], str(path))   # drugi eksport nie nadpisuje pierwszego

    def test_export_elsewhere_needs_a_second_officer(self):
        other = Path(self.tmp.name) / "pendrive"
        other.mkdir()
        with self.assertRaises(ValueError):
            self.d.export({"path": str(other)})
        with self.assertRaises(ValueError):
            self.d.export({"path": str(other / "brak"), "account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]})
        path = Path(self.d.export({"path": str(other), "account2": "dyzurny-2", "password2": self.envelopes["dyzurny-2"]})["file"])
        self.assertEqual(path.parent, other)
        self.assertIn(("dyzurny-1", "eksport"), [(e["account"], e["op"]) for e in self.d.view()["log"]])

    def test_close_writes_the_archive_and_removes_the_content(self):
        with self.assertRaises(ValueError):
            self.d.close({"confirm": "zamknij"})
        result = self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})
        archive = Path(result["file"])
        self.assertEqual(len(result["password"].split()), zamkniecie.ARCHIVE_WORDS)
        with self.assertRaises(ValueError):
            self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})       # raz
        target = Path(self.tmp.name) / "administrator"
        with self.assertRaises(database.LoginError):
            zamkniecie.open_archive(archive, self.envelopes["stanowisko"], target)
        zamkniecie.open_archive(archive, result["password"], target)
        rows = self.rows((target / "rejestr.csv").read_bytes())
        self.assertEqual(rows[0]["tresc"], "piwnica przy szkole")
        self.assertEqual(rows[-1]["rodzaj"], "zamkniecie")
        with contextlib.closing(sqlite3.connect(target / "baza.sqlite")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM received WHERE payload IS NOT NULL").fetchone(), (1,))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received WHERE payload IS NOT NULL"), (0,))
        snapshot = nosnik.Nosnik(self.medium.root).load(self.key)   # także bez resztek w wolnych stronach SQLite
        for text in ("piwnica przy szkole", "Proszę czekać przy wejściu", "Woda pitna przy szkole"):
            self.assertNotIn(text.encode(), snapshot)
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM replies WHERE text IS NOT NULL"), (0,))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM outbox WHERE length(payload) > 0 "
                                                        "AND kind IN (3, 4)"), (0,))
        view = self.d.view()
        self.assertEqual((view["reports"], view["closed"], view["bulletins"][0]["text"]), ([], self.now, ""))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))   # klucze zostają
        self.deliver(self.STATION, self.content)                # powtórka po zamknięciu: to samo RECEIVED
        self.assertEqual(self.sent[-1], (self.STATION, received_for(self.content)))

    def test_close_removes_the_plain_register_files_from_the_medium(self):
        first = Path(self.d.export({})["file"])
        self.now += 60
        Path(self.d.export({})["file"])
        archive = Path(self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})["file"])
        self.assertEqual(sorted(p.name for p in first.parent.iterdir()), [archive.name])
        log = self.d.view()["log"]
        self.assertEqual((log[0]["op"], log[0]["detail"]), ("eksport_usuniety", "usunięto 2 plików CSV"))

    def test_radio_silence_entries_go_to_the_register_and_the_order_to_the_stations(self):
        with self.assertRaises(ValueError):
            self.d.silence({"state": "wlacz", "organ": "wójt", "kiedy": "13:50"})
        mid = self.d.silence({"state": "polecenie", "organ": "wójt gminy Pruszcz", "kiedy": "30.10 13:50",
                              "bulletin": True})["bulletin"]
        self.assertEqual((self.d.view()["silence"]["organ"], self.d.view()["silence"]["account"]),
                         ("wójt gminy Pruszcz", "dyzurny-1"))
        self.tick()
        order = [wzorzec.decode_message(c)[4] for _, c in self.sent if wzorzec.decode_message(c)[2] == mid]
        self.assertEqual(order, ["CISZA RADIOWA od 30.10 13:50, polecenie: wójt gminy Pruszcz. Włącz CISZA na stacji. "
                                 "Pilne sprawy przez gońca."])
        self.d.silence({"state": "wlaczona", "organ": "wójt gminy Pruszcz", "kiedy": "30.10 13:55"})
        self.assertIsNone(self.d.silence({"state": "odwolana", "organ": "wójt gminy Pruszcz", "kiedy": "31.10 08:00"})["bulletin"])
        self.assertIsNone(self.d.view()["silence"])
        rows = self.rows(Path(self.d.export({})["file"]).read_bytes())
        self.assertEqual([r["tresc"] for r in rows if r["rodzaj"] == "cisza"],
                         ["polecenie ciszy otrzymane: wójt gminy Pruszcz, 30.10 13:50",
                          "cisza włączona na węźle: wójt gminy Pruszcz, 30.10 13:55",
                          "cisza odwołana: wójt gminy Pruszcz, 31.10 08:00"])
        with self.assertRaises(ValueError):   # stały tekst komunikatu nie mieści się w 192 B
            self.d.silence({"state": "polecenie", "organ": "ż" * 60, "kiedy": "ą" * 40, "bulletin": True})

    def test_archive_from_the_command_line(self):
        result = self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})
        target = Path(self.tmp.name) / "administrator"
        for password, expected in (("zle haslo", (3, "archive_failed")), (result["password"], (0, "archive_opened"))):
            out = io.StringIO()
            with unittest.mock.patch.object(sys, "stdin", io.StringIO(password + "\n")), contextlib.redirect_stdout(out):
                code = aplikacja.main(["archiwum", "--plik", result["file"], "--do", str(target)])
            self.assertEqual((code, json.loads(out.getvalue())["event"]), expected)
        self.assertTrue((target / "rejestr.csv").exists())

    def has_content(self, copy):
        return b"piwnica przy szkole" in kopie.Kopie.read(copy, self.key)[1]["baza"]

    def test_copies_from_before_closing_stay_until_removed(self):
        second = Path(self.tmp.name) / "drugi"
        second.mkdir()
        self.every_minute(5)   # kopia na dysku już ze zgłoszeniem
        self.d.backup({"path": str(second)})
        before = self.copies.files()
        self.assertTrue(self.has_content(before[0]))
        with self.assertRaises(ValueError):
            self.d.purge_copies({"kto": "administrator", "kiedy": "dziś"})
        self.now += 60
        self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})
        for _ in range(4):   # kopie co 5 min i przekazania zmiany po zamknięciu: kopie sprzed zamknięcia zostają
            self.every_minute(10)
            self.d.backup({"path": str(second)})
        after = [c for c in self.copies.files() if c not in before]
        self.assertEqual((set(before) <= set(self.copies.files()), len(after)), (True, kopie.KEEP))
        self.assertFalse(any(self.has_content(c) for c in after))   # po zamknięciu kopie bez treści
        on_second = kopie.Kopie(second / "wici-kopie").files()
        self.assertEqual((len(on_second), sum(self.has_content(c) for c in on_second)), (kopie.KEEP + 1, 1))
        self.assertEqual(self.d.purge_copies({"kto": "Jan Kowalski", "kiedy": "12.10 14:00", "path": str(second)}),
                         {"failed": []})
        self.assertEqual((self.copies.files(), kopie.Kopie(second / "wici-kopie").files()), ([], []))
        self.assertEqual(self.d.view()["copies_purged"], self.now)
        self.assertIn("kopie_usuniete", self.actions())
        self.every_minute(10)   # dalsza praca stanowiska ma znów kopie, już bez treści zamkniętego zdarzenia
        self.assertTrue(self.copies.files() and not any(self.has_content(c) for c in self.copies.files()))

    def test_destroy_leaves_no_data_and_ends_the_application(self):
        with self.assertRaises(ValueError):
            self.d.destroy({"confirm": "zniszcz"})
        self.assertTrue(self.copies.files())
        self.assertEqual(self.d.destroy({"confirm": "ZNISZCZ DANE"}), {"failed": []})
        self.assertEqual(self.quit, [1])
        self.assertEqual([p for p in self.medium.root.rglob("*") if p.is_file()], [])
        self.assertEqual(self.copies.files(), [])
        self.assertFalse(self.medium.exists())
        with self.assertRaises(panel.NotLoggedIn):
            self.d.current()


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
        self.stos = stos.Stos(tempfile.gettempdir(), "port", lambda s, c: self.got.append((s, c)), bytes(64),
                              log=lambda line: None)

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


class NodeDiagnosticsTest(unittest.TestCase):
    """S11: node state from INFO on its diagnostics port; only INFO is sent, other lines are the node log."""

    class Port:
        def __init__(self, test):
            self.test, self.written = test, []

        def write(self, data):
            self.written.append(data)

        def read(self, timeout):
            self.test.now += timeout
            reply, self.test.replies = self.test.replies[:1], self.test.replies[1:]
            return reply[0] if reply else b""

    def setUp(self):
        self.now, self.replies, self.changes = 0.0, [], []
        self.w = wezel.Wezel("port", lambda silence, first: self.changes.append((silence, first)),
                             monotonic=lambda: self.now)
        self.port = self.Port(self)

    def info(self, silence, **fields):
        return (json.dumps({"contract": 2, "silence": silence, "radio_ok": True, "tx_wait_ms": 0, **fields}) + "\n").encode()

    def test_silence_changes_are_reported_and_the_rest_is_status(self):
        self.assertIsNone(self.w.status())
        self.replies = [b"[12] radio rx ok\n" + self.info(False)[:20], self.info(False)[20:]]
        self.w.poll(self.port)
        self.assertEqual((self.changes, self.port.written), ([], [b"INFO\n"]))
        self.replies = [self.info(True, tx_wait_ms=42_000, radio_ok=False)]
        self.w.poll(self.port)
        self.replies = [self.info(True)]
        self.w.poll(self.port)
        self.replies = [self.info(False)]
        self.w.poll(self.port)
        self.assertEqual(self.changes, [(True, False), (False, False)])
        self.replies = [self.info(True, tx_wait_ms=42_000, radio_ok=False)]
        self.w.poll(self.port)
        self.assertEqual({k: v for k, v in self.w.status().items() if k != "age_s"},
                         {"silence": True, "radio_ok": False, "tx_wait_s": 42})

    def test_node_already_silent_at_start_is_recorded(self):
        self.replies = [self.info(True)]
        self.w.poll(self.port)
        self.assertEqual(self.changes, [(True, True)])

    def test_a_port_without_info_is_not_the_node(self):
        self.replies = [b"cos innego\n"]
        with self.assertRaises(ValueError):
            self.w.poll(self.port)
        self.assertIsNone(self.w.status())

    def test_diagnostics_is_the_other_interface_of_the_same_device(self):
        import types
        ports = [types.SimpleNamespace(device="/dev/ttyACM0", serial_number="A1"),
                 types.SimpleNamespace(device="/dev/ttyACM1", serial_number="A1"),
                 types.SimpleNamespace(device="/dev/ttyACM2", serial_number="B2")]
        tools = types.SimpleNamespace(list_ports=types.SimpleNamespace(comports=lambda: ports))
        with unittest.mock.patch.dict(sys.modules, {"serial": types.SimpleNamespace(tools=tools), "serial.tools": tools,
                                                    "serial.tools.list_ports": tools.list_ports}):
            self.assertEqual(wezel.find_diagnostics("/dev/ttyACM0"), "/dev/ttyACM1")
            self.assertIsNone(wezel.find_diagnostics("/dev/ttyACM2"))   # drugiego interfejsu nie ma
            self.assertIsNone(wezel.find_diagnostics("/dev/ttyUSB9"))

    def test_register_rows_and_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            medium, key, envelopes = medium_in(Path(tmp) / "nosnik")
            reception = przyjecie.Przyjecie(medium, key, lambda t, c: None, lambda m: None, log=lambda line: None)
            try:
                d = panel.Dyzur(reception, medium, key, FakeStack())
                d.wezel = self.w
                d.login("dyzurny-1", envelopes["dyzurny-1"])
                self.assertEqual((d.view()["node"]["diagnostics"], d.view()["node"]["info"]), (True, None))
                self.replies = [self.info(True)]
                self.w.poll(self.port)
                self.assertTrue(d.view()["node"]["info"]["silence"])
                reception.action("", "cisza_wezel", json.dumps({"silence": True, "start": True}))
                reception.action("", "cisza_wezel", json.dumps({"silence": False, "start": False}))
                rows = reception.call(lambda store: zamkniecie.register(store.db))
                self.assertEqual([r["tresc"] for r in rows if r["rodzaj"] == "cisza_wezel"],
                                 ["przełącznik CISZA węzła: włączony (przy starcie aplikacji)",
                                  "przełącznik CISZA węzła: wyłączony"])
            finally:
                reception.stop()


class PackageTest(unittest.TestCase):
    """S10b: pieces of the station package build (the whole build and the application from the package: CI)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def archive(self, files):
        path = self.tmp / "zrodla.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def test_library_takes_the_package_and_its_licence(self):
        archive = self.archive({"Reticulum-abc/RNS/__init__.py": b"x = 1\n", "Reticulum-abc/RNS/__pycache__/a.pyc": b"",
                                "Reticulum-abc/docs/manual.pdf": b"pdf", "Reticulum-abc/LICENSE": b"Reticulum License\n"})
        out = self.tmp / "pakiet"
        (out / "sources").mkdir(parents=True)
        pin = {"package": "RNS", "license": "LICENSE"}
        with unittest.mock.patch.object(build_stanowisko.usb, "fetch", return_value=archive):
            build_stanowisko.library("reticulum", pin, out)
        self.assertEqual(sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()),
                         ["lib/RNS/__init__.py", "licenses/reticulum.txt", "sources/zrodla.tar.gz"])

    def test_native_wheel_stays_with_its_runtime_and_keeps_license(self):
        import zipfile
        archive = self.tmp / "cryptography-test.whl"
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr("cryptography/__init__.py", "__version__ = '48.0.1'\n")
            wheel.writestr("cryptography/hazmat/bindings/_rust.abi3.so", b"native")
            wheel.writestr("cryptography-48.0.1.dist-info/licenses/LICENSE", b"licence")
        out = self.tmp / "pakiet"
        (out / "sources").mkdir(parents=True)
        with unittest.mock.patch.object(build_stanowisko.usb, "fetch", return_value=archive):
            build_stanowisko.wheel_library("cryptography", {}, "macos-arm64", out)
        self.assertEqual((out / "lib-platform/macos-arm64/cryptography/hazmat/bindings/_rust.abi3.so").read_bytes(),
                         b"native")
        self.assertEqual((out / "licenses/cryptography-LICENSE").read_bytes(), b"licence")
        self.assertEqual((out / "sources/cryptography-test.whl").read_bytes(), archive.read_bytes())

    def test_library_from_git_is_checked_by_its_commit(self):
        import subprocess
        repo = self.tmp / "LXMF"
        (repo / "LXMF").mkdir(parents=True)
        (repo / "LXMF" / "__init__.py").write_text("x = 1\n")
        (repo / "LICENSE").write_text("Reticulum License\n")
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                                         *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("add", ".")
        git("commit", "-q", "-m", "x")
        pin = {"repository": str(repo), "commit": git("rev-parse", "HEAD"), "package": "LXMF", "license": "LICENSE"}
        out = self.tmp / "pakiet"
        (out / "sources").mkdir(parents=True)
        with unittest.mock.patch.object(build_stanowisko.usb, "CACHE", self.tmp / "cache"):
            build_stanowisko.library("lxmf", pin, out)
            self.assertEqual((out / "lib" / "LXMF" / "__init__.py").read_text(), "x = 1\n")
            self.assertTrue((out / "sources" / f"lxmf-{pin['commit']}.tar.gz").is_file())
            with self.assertRaises(subprocess.CalledProcessError):   # commitu nie ma w repozytorium
                build_stanowisko.library("lxmf2", {**pin, "commit": "0" * 40}, out)

    def test_library_without_licence_stops_the_build(self):
        archive = self.archive({"LXMF-abc/LXMF/__init__.py": b""})
        with unittest.mock.patch.object(build_stanowisko.usb, "fetch", return_value=archive), \
                self.assertRaises(SystemExit):
            build_stanowisko.library("lxmf", {"package": "LXMF", "license": "LICENSE", "file": "x"}, self.tmp)

    def test_standard_library_without_tests_and_tk(self):
        for rel in ("json/__init__.py", "asyncio/base_events.py", "test/test_json.py", "tkinter/__init__.py",
                    "unittest/__init__.py", "idlelib/idle.py"):
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text("")
        self.assertEqual(sorted(build_stanowisko.stdlib_files(self.tmp)), ["asyncio.base_events", "json", "unittest"])

    def test_reference_model_goes_next_to_the_application(self):
        build_stanowisko.application(self.tmp)
        app = self.tmp / "app" / "wici"
        for rel in ("stanowisko/reference.py", "stanowisko/schema.sql", "stanowisko/ui/index.html", "slowa.txt", "web.py"):
            self.assertTrue((app / rel).is_file(), rel)
        self.assertEqual(list(app.rglob("__pycache__")), [])

    def test_out_is_replaced_only_after_a_station_package_build(self):
        (self.tmp / "dokumenty.txt").write_text("cudze")
        with self.assertRaises(SystemExit):
            build_stanowisko.build(self.tmp, [])
        self.assertTrue((self.tmp / "dokumenty.txt").exists())


@unittest.skipUnless((HAS_STACK or PACKAGE) and shutil.which("node") and os.name == "posix",
                     "Reticulum, LXMF and pyserial, Node.js or a pseudo-terminal not available")
class SimulatorTest(unittest.TestCase):
    """S10: the application in the simulator world instead of post.cpp (swiat.mjs --stanowisko), on the node data
    port over TCP: a TEST from a station configured with the card from `przygotuj` goes to quarantine, and after
    approval RECEIVED reaches the station (the intent ends on DELIVERED); S11: the node CISZA switch reaches the
    panel and the log through the node diagnostics port. With WICI_STANOWISKO_PACKAGE the
    application runs from the built station package instead of this Python."""

    IFAC = "5749434953494d554c41544f52305f30"   # sieć ćwiczeniowa świata (web/world.js)

    def setUp(self):
        import subprocess
        from wici import usbproto
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "software" / "laptop"), "WICI_STATE": str(tmp / "stan")}
        app = [str(Path(PACKAGE) / "stanowisko.sh")] if PACKAGE else [sys.executable, "-m", "wici.stanowisko"]
        out = subprocess.run([*app, "przygotuj", "--nosnik", str(tmp / "nosnik"),
                              "--dyzurni", "2", "--paczka", str(tmp / "paczka.json"), "--karta", str(tmp / "karta.json"),
                              "--iteracje", str(FAST)], capture_output=True, text=True, env=env, check=True)
        self.envelopes = json.loads(out.stdout.splitlines()[-1])["envelopes"]
        card = json.loads((tmp / "karta.json").read_text(encoding="utf-8"))
        (tmp / "stacja.json").write_text(json.dumps({
            "role": "stacja", "addresses": ["Szkoła Podstawowa nr 2, wejście B"],
            "receiver": {"main": card["main"], "backup": card["backup"]}, "stations": 12,
            "phrases": [["osoba na wózku", "людина на візку", "wheelchair user"]], "ifac": self.IFAC,
            "radio": {"profile": "p1"}}), encoding="utf-8")
        self.world = subprocess.Popen(["node", str(ROOT / "software" / "simulator" / "swiat.mjs"), "--port", "0",
                                       "--http", "0", "--wezel", "0", "--stanowisko", str(tmp / "karta.json"),
                                       "--station", str(tmp / "stacja.json")],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(self.world.wait, 10)
        self.addCleanup(self.world.stdin.close)
        self.addCleanup(self.world.stdout.close)
        lines = []
        for line in self.world.stdout:
            if line.strip() == "gotowe":
                break
            lines.append(line.strip())
        node = next(x for x in lines if x.startswith("węzeł ")).split()[1]
        diagnostics = next(x for x in lines if x.startswith("węzeł-diagnostyka ")).split()[1]
        station = next(x for x in lines if x.startswith("stacja 1 ")).split()[2]
        self.assertFalse(any(x.startswith("uwaga:") for x in lines), lines)
        self.app = subprocess.Popen([*app, "start", "--nosnik", str(tmp / "nosnik"),
                                     "--port", node, "--diagnostyka", diagnostics, "--panel", "0", "--bez-przegladarki", "--kopie", str(tmp / "kopie"), "--koniec-wejscia"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, env=env)
        self.addCleanup(self.app.wait, 20)
        self.addCleanup(self.app.stdin.close)
        self.addCleanup(self.app.stdout.close)
        self.app.stdin.write(self.envelopes["stanowisko"] + "\n")
        self.app.stdin.flush()
        ready = json.loads(self.app.stdout.readline())
        self.assertEqual(ready["event"], "ready")
        self.panel_url = urlsplit(ready["panel"])
        self.station = usbproto.Station(station).start()
        self.addCleanup(self.station.stop)
        self.wait(lambda: self.station.state["phase"] == "connected", 30)

    def wait(self, test, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = test()
            if value:
                return value
            time.sleep(1)
        self.fail("timeout")

    def http(self, method, path, body=None, cookie=None):
        import http.client
        c = http.client.HTTPConnection(self.panel_url.hostname, self.panel_url.port, timeout=10)
        headers = {"Host": self.panel_url.netloc, "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        data, set_cookie = r.read(), r.getheader("Set-Cookie")
        c.close()
        return r.status, set_cookie, data

    def test_test_message_through_the_world_and_received_back(self):
        nonce = secrets.token_hex(8)
        self.assertEqual(self.station.call(lambda link: link.request("test", nonce=nonce))["type"], "stored")
        self.wait(lambda: json.loads(self.http("GET", "/health")[2])["counts"]["quarantined"], 240)
        _, cookie, _ = self.http("GET", f"/start?{self.panel_url.query}")
        cookie = cookie.split(";")[0]
        self.assertEqual(self.http("POST", "/api/operator/login", {"account": "dyzurny-1",
                                   "password": self.envelopes["dyzurny-1"]}, cookie)[0], 200)
        item = json.loads(self.http("GET", "/api/operator/queue", cookie=cookie)[2])["quarantine"][0]
        self.assertEqual(self.http("POST", "/api/operator/quarantine", {**{k: item[k] for k in ("source", "id", "revision")},
                                   "decision": "approve"}, cookie)[0], 200)
        node = lambda: json.loads(self.http("GET", "/api/operator/queue", cookie=cookie)[2])["node"]
        self.wait(lambda: node()["waiting"] == 0 and node()["in_flight"] == 0, 240)   # RECEIVED dostarczone

        # S11: przełącznik CISZA węzła przez port diagnostyki, bez zmian w KISS.
        self.assertFalse(node()["info"]["silence"])
        self.world.stdin.write("silence wezel on\n")
        self.world.stdin.flush()
        self.wait(lambda: node()["info"]["silence"], 30)
        log = json.loads(self.http("GET", "/api/operator/queue", cookie=cookie)[2])["log"]
        self.assertEqual([e["op"] for e in log if e["op"] == "cisza_wezel"], ["cisza_wezel"])


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
        import RNS
        cls.medium, cls.key, envelopes = medium_in(work / "nosnik", identity=RNS.Identity().get_private_key())
        cls.stos = stos.Stos(cls.medium.network, cls.node.ready["usb"], received, cls.medium.identity(cls.key),
                             log=lambda line: None)
        cls.station_password = envelopes["stanowisko"]
        cls.reception = przyjecie.Przyjecie(cls.medium, cls.key, cls.stos.send, cls.stos.outcome, log=lambda line: None)
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

    def test_6_identity_comes_from_the_medium(self):
        import RNS
        key = nosnik.Nosnik(self.medium.root).unlock(self.station_password)
        self.assertEqual(RNS.Identity.from_bytes(self.medium.identity(key)).hash, self.stos.identity.hash)
        self.assertNotIn(self.stos.identity.get_private_key(), (self.medium.root / "tozsamosc").read_bytes())


if __name__ == "__main__":
    unittest.main()
