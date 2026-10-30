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
from wici.stanowisko import __main__ as aplikacja, kopie, nosnik, panel, przyjecie, stos, wysylka, wzorzec, zamkniecie  # noqa: E402

PROGRAM = os.environ.get("WICI_HOST_PROGRAM")
# Pakiet stanowiska (build_stanowisko.py): SimulatorTest uruchamia wtedy aplikację jego skryptem stanowisko.sh.
PACKAGE = os.environ.get("WICI_STANOWISKO_PACKAGE")
HAS_STACK = all(importlib.util.find_spec(m) for m in ("RNS", "LXMF", "serial"))
FAST = 1_000   # iteracje PBKDF2 w testach (najmniej, ile przyjmuje odczyt)


def medium_in(root, officers=2, identity=None):
    """A prepared medium with fast PBKDF2: (medium, data key, envelopes)."""
    return nosnik.Nosnik.create(root, officers, identity or bytes(range(64)), FAST)


def durable(medium, key, sql, args=()):
    """Query the newest snapshot on the medium, as a restarted application would see it."""
    body = nosnik.Nosnik(medium.root).load(key)
    if body is None:
        return None
    with contextlib.closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(body)
        return db.execute(sql, args).fetchone()


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

    def test_snapshots_are_sealed_and_an_interrupted_write_keeps_the_previous(self):
        self.medium.save(self.key, b"pierwsza piwnica")
        self.medium.save(self.key, b"druga piwnica")
        self.assertNotIn(b"piwnica", self.files())
        newest = self.root / "baza" / self.medium.last
        newest.write_bytes(newest.read_bytes()[:-10])   # zanik zasilania w trakcie zapisu
        self.assertEqual(nosnik.Nosnik(self.root).load(self.key), b"pierwsza piwnica")
        self.assertIsNone(nosnik.Nosnik(self.root).load(os.urandom(32)))

    def test_identity_is_sealed_with_the_data_key(self):
        self.assertEqual(self.medium.identity(self.key), bytes(range(64)))
        self.assertNotIn(bytes(range(64)), self.files())
        with self.assertRaises(database.StorageError):
            self.medium.identity(os.urandom(32))

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
        with unittest.mock.patch.object(kopie.os, "replace", side_effect=OSError("zanik zasilania")):
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
    """Station card as `card` over USB returns it (protokol-usb.md)."""
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
        new = self.d.new_password({"account": "dyzurny-2"})["password"]
        self.medium.login("dyzurny-2", new, self.key)
        station = self.d.new_password({"account": "stanowisko"})["password"]
        self.assertEqual(nosnik.Nosnik(self.medium.root).unlock(station), self.key)

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
            status, _, data = request_("GET", "/api/operator/queue", headers=auth)
            self.assertEqual((status, json.loads(data)["user"]), (200, "dyzurny-1"))
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
        self.medium.save = lambda key, body: (saves.append(1), real(key, body))
        self.deliver(self.STATION, request())                  # przyjęcie: migawka przed RECEIVED
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

    def test_copies_removed_only_after_closing_and_not_made_again(self):
        second = Path(self.tmp.name) / "drugi"
        second.mkdir()
        self.d.backup({"path": str(second)})
        self.assertTrue(self.copies.files())
        with self.assertRaises(ValueError):
            self.d.purge_copies({"kto": "administrator", "kiedy": "dziś"})
        self.d.close({"confirm": "ZAMKNIJ ZDARZENIE"})
        self.assertEqual(self.d.purge_copies({"kto": "Jan Kowalski", "kiedy": "12.10 14:00", "path": str(second)}),
                         {"failed": []})
        self.every_minute(15)
        self.assertEqual((self.copies.files(), kopie.Kopie(second / "wici-kopie").files()), ([], []))
        self.assertEqual(self.d.view()["copies_purged"], self.now - 15 * 60)
        self.assertIn("kopie_usuniete", self.actions())

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
        pin = {"package": "RNS", "license": "LICENSE", "file": "Reticulum-abc.tar.gz"}
        with unittest.mock.patch.object(build_stanowisko.usb, "fetch", return_value=archive):
            build_stanowisko.library("reticulum", pin, out)
        self.assertEqual(sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()),
                         ["lib/RNS/__init__.py", "licenses/reticulum.txt", "sources/Reticulum-abc.tar.gz"])

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
    approval RECEIVED reaches the station (the intent ends on DELIVERED). With WICI_STANOWISKO_PACKAGE the
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
        station = next(x for x in lines if x.startswith("stacja 1 ")).split()[2]
        self.assertFalse(any(x.startswith("uwaga:") for x in lines), lines)
        self.app = subprocess.Popen([*app, "start", "--nosnik", str(tmp / "nosnik"),
                                     "--port", node, "--panel", "0", "--bez-przegladarki", "--kopie", str(tmp / "kopie")],
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
        self.wait(lambda: node()["waiting"] == 0, 240)


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
