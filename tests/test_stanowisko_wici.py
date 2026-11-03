# SPDX-License-Identifier: MIT
"""WICI-Link admission at the receiving station: permanent and transient failures, HACK deadline, identity cache.

docs/spec/stanowisko-osp.md, „Przyjęcie koperty WICI-Link”. With WICI_POMIAR_HACK=1 the timing test prints the
measured admission path (queue and database work) for a realistic database.
"""

import importlib.util
import json
import os
import statistics
import sys
import threading
import time
import unittest
import unittest.mock

from tests.test_stanowisko import OnlineLink, StationTestCase, durable, received_for, request
from wici.stanowisko import nosnik, przyjecie, wysylka, zamkniecie

HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None


@unittest.skipUnless(HAS_CRYPTO, "cryptography for D21 envelope")
class WiciAdmissionTest(StationTestCase):
    """A numbered receiver (net 100, main 2, backup 3) and trusted station 4."""

    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives.asymmetric import x25519
        from wici import envelope
        from wici.stanowisko import envelope_inbox
        self.envelope, self.inbox = envelope, envelope_inbox
        self.station_private = bytes(range(32, 64))
        receiver_private = bytes(range(32))
        self.receiver_public = x25519.X25519PrivateKey.from_private_bytes(receiver_private).public_key().public_bytes_raw()
        station_key = (x25519.X25519PrivateKey.from_private_bytes(self.station_private).public_key().public_bytes_raw()
                       + bytes(range(32, 64)))
        self.source = nosnik.lxmf_address(station_key)
        self.card = nosnik.receiver_card(nosnik.public_identity(receiver_private + bytes(range(32))),
                                         bytes(range(64, 128)), 100, 2, 3)
        self.medium.save_identity(self.key, receiver_private + bytes(range(32)))
        self.medium.save_card(self.key, self.card)

        def register(store):
            store.add_trusted(self.source, station_key, ("dyzurny-1", "dyzurny-2"))
            store.db.execute("INSERT INTO numery VALUES(?,?,?,?)", (100, 4, self.source, station_key))
        self.reception.call(register)

    def seal(self, counter, content=None, sender=4, recipient=2, max_payload=236):
        key = self.envelope.derive_key(self.station_private, self.receiver_public, 100, sender, recipient, own_id=sender)
        return self.envelope.seal(key, sender, recipient, counter, content or request(), max_payload)

    def proof(self, counter, counters, sender=4, recipient=2):
        key = self.envelope.derive_key(self.station_private, self.receiver_public, 100, sender, recipient, own_id=sender)
        plain = b"".join(c.to_bytes(4, "big") for c in counters)
        return self.envelope.seal(key, sender, recipient, counter, plain, 236, self.envelope.TYPE_PROOF)[0]

    def send(self, content):
        """An intent for station 4 and one envelope of it through send_wici; returns its envelope counter."""
        def go(store):
            with store.db:
                if store.db.execute("SELECT 1 FROM outbox WHERE payload=?", (content,)).fetchone() is None:
                    self.reception.wysylka.enqueue(store.db, self.source, wysylka.RECEIVED, "x", 1, content)
            return self.reception.send_wici(OnlineLink(), self.source, content)
        return int.from_bytes(self.reception.call(go)[0][5:9], "big")

    def open_intents(self):
        return self.reception.call(lambda s: s.db.execute(
            "SELECT payload, next_try FROM outbox WHERE done=0 ORDER BY seq").fetchall())

    def test_station_proof_closes_the_intent_also_after_a_resend(self):
        # E1: a relay's HACK left the intent open; the station's proof of any of its counters closes it.
        content = received_for(request())
        first, second = self.send(content), self.send(content)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.open_intents()), 1)
        self.assertEqual(self.admit(self.proof(0, [first])), "proof")   # the late proof of the first copy
        self.assertEqual(self.open_intents(), [])
        self.assertEqual(self.admit(self.proof(0, [first])), "duplicate")   # replay: no second effect

    def test_proof_of_unknown_counters_closes_nothing_but_counts_as_contact(self):
        content = received_for(request())
        self.send(content)
        self.reception.call(lambda s: s.db.execute("UPDATE outbox SET next_try=9e9, forwarded=2"))
        self.assertEqual(self.admit(self.proof(0, [777, 778])), "proof")
        self.assertEqual(self.open_intents(), [(content, 0)])   # still open, sent again at once
        # A proof to the other receiver number is not for this identity.
        self.assertEqual(self.admit(self.proof(1, [0], recipient=3)), "unauthenticated")

    def test_a_proof_is_not_an_sa1_envelope(self):
        from wici import envelope
        frame = self.proof(0, [5])
        key = self.envelope.derive_key(self.station_private, self.receiver_public, 100, 4, 2, own_id=4)
        with self.assertRaises(envelope.EnvelopeError):
            envelope.open_part(key, frame)   # SA1 callers never see a proof
        self.assertEqual(envelope.open_part(key, frame, (envelope.TYPE_SA1, envelope.TYPE_PROOF)).plaintext,
                         bytes([0, 0, 0, 5]))
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(key, 4, 2, 1, b"abc", 236, envelope.TYPE_PROOF)   # whole u32 counters only

    def admit(self, frame, net_id=100, timeout=5):
        return self.reception.admit_wici_frame(net_id, frame, timeout)

    def rejected(self):
        return self.reception.call(lambda s: przyjecie.envelope_rejections(s.db))

    def test_frame_not_authenticated_is_counted_and_acknowledged_without_storage(self):
        """The network key does not name the sender: no bytes, no snapshot; the alarm counts in memory, and the
        HACK still goes, so relays next to the root do not turn away from it."""
        forged = bytearray(self.seal(8)[0])
        forged[-1] ^= 1
        cases = {
            "unknown station number": (100, self.seal(7, sender=9)[0]),
            "wrong receiver number": (100, self.seal(101, recipient=7)[0]),
            "envelope authentication failed": (100, bytes(forged)),
            "invalid envelope length": (100, bytes(5)),
            "receiver identity not bound to this network": (101, self.seal(11)[0]),
        }
        with unittest.mock.patch.object(self.medium, "save", wraps=self.medium.save) as save:
            for reason, (net_id, frame) in cases.items():
                with self.subTest(reason):
                    self.assertEqual(self.admit(frame, net_id=net_id), "unauthenticated")
                    with self.assertRaises(przyjecie.NotAuthenticated) as raised:   # the raising form
                        self.reception.receive_envelope_frame(net_id, frame)
                    self.assertEqual(raised.exception.reason, reason)
        save.assert_not_called()
        self.assertEqual(self.reception.unauthenticated["unknown station number"]["count"], 2)
        self.assertEqual(self.reception.unauthenticated["wrong receiver number"]["count"], 2)
        self.assertEqual(self.reception.unauthenticated["unknown station number"]["sender"], 9)
        self.assertEqual(len(self.reception.unauthenticated), len(cases))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_rejected"), (0,))
        self.assertEqual(self.reception.rejected["total"], 0)

    def test_station_added_later_is_admitted_on_its_sa1_retry(self):
        """Nothing of the unknown number's frame is kept; the station's SA1 retry (new counter) is admitted."""
        self.assertEqual(self.admit(self.seal(7, sender=9)[0]), "unauthenticated")
        # The station's card now carries number 9 (one number per station key, so the entry moves).
        self.reception.call(lambda s: s.db.execute("UPDATE numery SET station=9 WHERE station=4"))
        self.assertEqual(self.admit(self.seal(8, sender=9)[0]), "complete")
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))

    def test_authenticated_permanent_failure_is_set_aside_durably_then_acknowledged(self):
        self.assertEqual(self.admit(self.seal(100)[0]), "complete")
        frame = self.seal(100 - self.envelope.WINDOW)[0]
        self.assertEqual(self.admit(frame), "rejected")
        self.assertEqual(durable(self.medium, self.key, "SELECT net_id, sender, count, frame FROM env_rejected"),
                         (100, 4, 1, frame))
        with unittest.mock.patch.object(self.medium, "save", wraps=self.medium.save) as save:
            self.assertEqual(self.admit(frame), "rejected")   # the same bytes again: one row, counted,
        save.assert_not_called()                              # HACK without a new snapshot
        self.assertEqual(self.reception.rejected["total"], 2)
        summary = self.rejected()
        self.assertEqual((summary["total"], len(summary["rows"]), summary["rows"][0]["count"]), (2, 1, 2))
        self.assertIn("replay window", summary["rows"][0]["reason"])
        self.assertEqual(self.reception.counts["envelope_rejected"], 2)
        with self.assertRaises(self.inbox.PermanentRejection):   # the raising form keeps the reason
            self.reception.receive_envelope_frame(100, frame)
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))

    def test_every_authenticated_permanent_failure_is_set_aside(self):
        self.assertEqual(self.admit(self.seal(100)[0]), "complete")
        cases = {
            "SA1": self.seal(102, content=b"\x01garbage")[0],
            "counter outside replay window": self.seal(100 - self.envelope.WINDOW)[0],
        }
        for reason, frame in cases.items():
            with self.subTest(reason):
                self.assertEqual(self.admit(frame), "rejected")
        reasons = [row["reason"] for row in self.rejected()["rows"]]
        self.assertEqual(len(reasons), 2)
        for reason in cases:
            self.assertTrue(any(reason in r for r in reasons), (reason, reasons))
        # A whole envelope over a pending fragment of the same counter.
        self.assertEqual(self.admit(self.seal(110, request(text="x" * 96), max_payload=153)[1]), "partial")
        self.assertEqual(self.admit(self.seal(110)[0]), "rejected")
        self.assertIn("pending fragment", self.rejected()["rows"][0]["reason"])
        # Nothing was admitted by the rejected frames, and the fragment is still pending.
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_parts"), (1,))

    def test_transient_failures_get_no_hack_and_are_not_set_aside(self):
        for counter in range(1, 1 + self.inbox.PER_SENDER):
            self.assertEqual(self.admit(self.seal(counter, request(text="x" * 96), max_payload=153)[1]), "partial")
        with self.assertRaises(self.envelope.EnvelopeError) as raised:   # fragment inbox full
            self.admit(self.seal(40, request(text="x" * 96), max_payload=153)[1])
        self.assertNotIsInstance(raised.exception, self.inbox.PermanentRejection)
        self.assertEqual(self.admit(self.seal(200)[0]), "complete")
        old = self.seal(200 - self.envelope.WINDOW)[0]
        with unittest.mock.patch.object(self.medium, "save", side_effect=OSError("medium removed")):
            with self.assertRaises(OSError):
                self.admit(self.seal(201)[0])
            # A permanent rejection that cannot be stored durably is no HACK either.
            with self.assertRaises(nosnik.StorageError):
                self.admit(old)
        self.assertEqual(self.admit(old), "rejected")   # the retry is stored and HACKed
        self.assertEqual(durable(self.medium, self.key, "SELECT count FROM env_rejected"), (2,))

    def test_set_aside_keeps_the_first_frames_and_counts_the_rest(self):
        """Nothing evicts stored evidence: over REJECTED_MAX the frames are only counted."""
        self.assertEqual(self.admit(self.seal(500)[0]), "complete")
        frames = [self.seal(counter)[0] for counter in range(4)]   # all outside the replay window
        with unittest.mock.patch.object(przyjecie, "REJECTED_MAX", 3):
            for frame in frames:
                self.assertEqual(self.admit(frame), "rejected")
        rows = self.rejected()["rows"]
        self.assertEqual([row["frame"] for row in rows], [f.hex() for f in reversed(frames[:3])])
        self.reception.call(lambda s: self.reception.tick())
        self.assertEqual(durable(self.medium, self.key, "SELECT sender, count FROM env_rejected_overflow"), (4, 1))

    def test_frames_over_the_sender_cap_are_counted_not_stored(self):
        self.assertEqual(self.admit(self.seal(500)[0]), "complete")
        with unittest.mock.patch.object(przyjecie, "REJECTED_PER_SENDER", 2):
            for counter in range(2):
                self.assertEqual(self.admit(self.seal(counter)[0]), "rejected")
            with unittest.mock.patch.object(self.medium, "save", wraps=self.medium.save) as save:
                self.assertEqual(self.admit(self.seal(2)[0]), "rejected")   # HACK, bytes not kept
            save.assert_not_called()
        self.reception.call(lambda s: self.reception.tick())   # the count reaches the medium with a snapshot
        self.assertEqual(durable(self.medium, self.key, "SELECT sender, count FROM env_rejected_overflow"), (4, 1))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_rejected"), (2,))
        summary = self.rejected()
        self.assertEqual((summary["frames"], summary["total"], summary["overflow"][0]["count"]), (2, 3, 1))
        self.assertEqual(self.reception.rejected, {k: summary[k] for k in ("frames", "total", "newest")})

    def test_a_caller_error_in_the_inbox_is_not_blamed_on_the_station(self):
        inbox = self.reception.call(lambda s: self.inbox.Inbox(s.db, 100, lambda: True))
        key = self.envelope.derive_key(self.station_private, self.receiver_public, 100, 4, 2, own_id=4)
        part = self.envelope.open_part(key, self.seal(1)[0])
        for now, key in ((1.5, key), (1, key[:31])):
            with self.subTest(now=now), self.assertRaises(self.envelope.EnvelopeError) as raised:
                self.reception.call(lambda s: inbox.receive(part, key, now, lambda full: None))
            self.assertNotIsInstance(raised.exception, self.inbox.PermanentRejection)

    def test_panel_alarm_shows_every_frame_acknowledged_without_admission(self):
        self.assertFalse(self.reception.envelope_alarm()["active"])
        self.assertEqual(self.admit(self.seal(7, sender=9)[0]), "unauthenticated")
        alarm = self.reception.envelope_alarm()
        self.assertTrue(alarm["active"])
        self.assertEqual(alarm["unauthenticated"]["unknown station number"]["sender"], 9)
        self.assertEqual(alarm["total"], 0)
        self.assertEqual(self.admit(self.seal(400)[0]), "complete")
        self.assertEqual(self.admit(self.seal(400 - self.envelope.WINDOW)[0]), "rejected")
        alarm = self.reception.envelope_alarm()
        self.assertEqual((alarm["frames"], alarm["total"], alarm["rows"][0]["sender"]), (1, 1, 4))
        self.assertIn("replay window", alarm["rows"][0]["reason"])
        # Closing the event clears the durable part; the in-memory count lasts until the restart.
        self.reception.call(lambda s: zamkniecie.purge(s.db))
        alarm = self.reception.envelope_alarm()
        self.assertEqual((alarm["total"], alarm["rows"]), (0, []))
        self.assertTrue(alarm["active"])

    def test_closing_the_event_removes_envelope_content(self):
        self.assertEqual(self.admit(self.seal(300)[0]), "complete")
        self.assertEqual(self.admit(self.seal(300 - self.envelope.WINDOW)[0]), "rejected")
        self.assertEqual(self.admit(self.seal(301, request(text="x" * 96), max_payload=153)[1]), "partial")
        self.reception.call(lambda s: zamkniecie.purge(s.db))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_rejected"), (0,))
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM env_parts"), (0,))
        self.reception.call(lambda s: self.reception.tick())
        self.assertEqual(self.reception.rejected["frames"], 0)

    def test_late_decision_sends_no_hack_but_admission_completes(self):
        hold, holding = threading.Event(), threading.Event()
        self.reception.jobs.put(lambda: (holding.set(), hold.wait(5)))
        holding.wait(5)
        frame = self.seal(50)[0]
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.admit(frame, timeout=0.05)
        self.assertLess(time.monotonic() - started, 0.5)
        hold.set()
        self.reception.call(lambda s: None)   # the queued admission has run
        self.assertEqual(durable(self.medium, self.key, "SELECT count(*) FROM received"), (1,))
        self.assertEqual(self.admit(frame), "duplicate")   # the station's retry gets its HACK

    def test_identity_is_read_once_per_session(self):
        with unittest.mock.patch.object(self.medium, "card", wraps=self.medium.card) as card, \
                unittest.mock.patch.object(self.medium, "identity", wraps=self.medium.identity) as identity:
            for counter in (60, 61, 62):
                self.assertEqual(self.admit(self.seal(counter)[0]), "complete")
        self.assertEqual((card.call_count, identity.call_count), (1, 1))

    def test_admission_timing_with_a_realistic_database(self):
        """About 2000 reports with intents and 5000 log entries (a long event); the path must fit the budget."""
        def fill(store):
            for i in range(2000):
                store.receive(self.source, request(text="piwnica, dwie osoby starsze, woda do kostek " * 2), True)
            with store.db:
                store.db.executemany("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                                     [(self.now, "dyzurny-1", "decyzja", "x" * 80)] * 5000)
        self.reception.call(fill)
        size = self.reception.call(lambda s: len(s.db.serialize()))
        timings = {"complete": [], "duplicate": []}
        for counter in range(100, 130):
            frame = self.seal(counter)[0]
            for kind in timings:
                started = time.monotonic()
                self.assertEqual(self.admit(frame), kind)
                timings[kind].append((time.monotonic() - started) * 1000)
        if os.environ.get("WICI_POMIAR_HACK"):
            for kind, values in timings.items():
                values.sort()
                print(f"\nbaza {size / 1e6:.1f} MB, {kind}: mediana {statistics.median(values):.1f} ms, "
                      f"p90 {values[int(len(values) * 0.9)]:.1f} ms, max {values[-1]:.1f} ms")
        # Loose bound for slow test machines; the measured numbers are in the report.
        self.assertLess(statistics.median(timings["duplicate"]), 1000)


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("RNS", "LXMF")) and os.name == "posix",
                     "Reticulum and LXMF, POSIX signals")
class StartLifetimeTest(unittest.TestCase):
    """`start` with a piped password keeps running after the end of stdin; SIGTERM ends it with the last
    snapshot; --koniec-wejscia restores the end-of-stdin stop for supervisors that hold a pipe."""

    def run_app(self, *extra):
        import subprocess
        import tempfile
        from pathlib import Path
        from tests.test_stanowisko import ROOT, medium_in
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        medium, _, envelopes = medium_in(tmp / "nosnik")
        env = {**os.environ, "PYTHONPATH": str(ROOT / "software" / "laptop"), "WICI_STATE": str(tmp / "stan")}
        app = subprocess.Popen([sys.executable, "-m", "wici.stanowisko", "start", "--nosnik", str(medium.root),
                                "--port", str(tmp / "brak-portu"), "--panel", "0", "--bez-przegladarki",
                                "--diagnostyka", "brak", "--kopie", str(tmp / "kopie"), *extra],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, env=env)
        self.addCleanup(lambda: app.poll() is None and app.kill())
        self.addCleanup(app.stdout.close)
        app.stdin.write(envelopes["stanowisko"] + "\n")
        app.stdin.close()   # as `echo HASŁO | python -m wici.stanowisko start …`
        self.assertEqual(json.loads(app.stdout.readline())["event"], "ready")
        return app

    def test_end_of_stdin_does_not_stop_and_sigterm_does(self):
        import signal
        app = self.run_app()
        time.sleep(1.5)
        self.assertIsNone(app.poll())
        app.send_signal(signal.SIGTERM)
        self.assertEqual(app.wait(20), 0)

    def test_explicit_flag_stops_at_end_of_stdin(self):
        self.assertEqual(self.run_app("--koniec-wejscia").wait(20), 0)


if __name__ == "__main__":
    unittest.main()
