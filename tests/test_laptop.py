# SPDX-License-Identifier: MIT
"""Laptop application, stage 1 (software/laptop): preparation mode over the USB contract "usb":2.

Unit tests cover the configure document against the firmware limits and the SA1 text rule of the
reference model, the protocol client against a scripted station, the Windows kernel32 structures, the
append-only journal and the access rules of the local panel. With Node.js the whole preparation runs
against the bench-b firmware image of the simulator: discovery, `prep_required`, preparation button,
configure, config_get and the station card."""

from pathlib import Path
import ast
import base64
import ctypes
import hashlib
import http.client
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LAPTOP = ROOT / "software" / "laptop"
sys.path.insert(0, str(LAPTOP))
sys.path.insert(0, str(ROOT / "software" / "reference"))

from wici import configdoc, database, serialport, session, store, syscrypto, usbproto  # noqa: E402
from wici.prep import OperationError, Prep  # noqa: E402
from wici import web  # noqa: E402
from wici.web import Panel, serve  # noqa: E402
from wici import __main__ as wici_main  # noqa: E402
import reference  # noqa: E402

MAIN_KEY, BACKUP_KEY = bytes(range(64)), bytes(range(64, 128))


def card(key):
    return {"lxmf": configdoc.destination(key, "lxmf.delivery").hex(), "key": key.hex()}


def station_doc(**changes):
    doc = {"role": "stacja", "addresses": ["Szkoła Podstawowa nr 2, wejście B"],
           "receiver": {"main": card(MAIN_KEY), "backup": card(BACKUP_KEY)}, "stations": 12,
           "phrases": [["osoba na wózku", "людина на візку", "wheelchair user"]], "ifac": "11" * 16,
           "radio": {"profile": "p1"}}
    doc.update(changes)
    return doc


class ConfigDocTest(unittest.TestCase):
    def fields(self, doc):
        return [f for f, _ in configdoc.check(doc)]

    def test_valid_documents(self):
        self.assertEqual(configdoc.check(station_doc()), [])
        self.assertEqual(configdoc.check({"role": "wezel", "ifac": "ab" * 16, "radio": {"profile": "lora-sf7"}}), [])

    def test_limits_follow_the_firmware(self):
        self.assertEqual(self.fields(station_doc(addresses=[])), ["addresses"])
        self.assertEqual(self.fields(station_doc(addresses=["a"] * 9)), ["addresses"])
        self.assertEqual(self.fields(station_doc(addresses=["x" * 64, "ą" * 33])), ["addresses.1"])
        self.assertEqual(self.fields(station_doc(addresses=[""])), ["addresses.0"])
        self.assertEqual(self.fields(station_doc(stations=0)), ["stations"])
        self.assertEqual(self.fields(station_doc(stations=1001)), ["stations"])
        self.assertEqual(self.fields(station_doc(stations=True)), ["stations"])
        self.assertEqual(self.fields(station_doc(phrases=[["a", "", ""]] * 12)), ["phrases"])
        self.assertEqual(self.fields(station_doc(phrases=[["", "b", "c"]])), ["phrases.0.0"])   # PL obowiązkowa
        self.assertEqual(self.fields(station_doc(phrases=[["a", "b"]])), ["phrases.0"])
        self.assertEqual(self.fields(station_doc(phrases=[["a", "", "x" * 97]])), ["phrases.0.2"])
        self.assertEqual(self.fields(station_doc(ifac="AB" * 16)), ["ifac"])                   # małe cyfry
        self.assertEqual(self.fields(station_doc(radio={"profile": "fsk"})), ["radio"])
        self.assertEqual(self.fields(station_doc(colour=1)), ["colour"])
        self.assertEqual(self.fields({"role": "wezel", "ifac": "11" * 16, "radio": {"profile": "p1"}, "stations": 2}),
                         ["stations"])

    def test_receiver_card_must_be_consistent(self):
        bad = card(MAIN_KEY)
        bad["lxmf"] = "00" * 16
        self.assertEqual(self.fields(station_doc(receiver={"main": bad, "backup": card(BACKUP_KEY)})), ["receiver.main.lxmf"])
        self.assertEqual(self.fields(station_doc(receiver={"main": card(MAIN_KEY), "backup": card(MAIN_KEY)})),
                         ["receiver.backup"])
        self.assertEqual(self.fields(station_doc(receiver={"main": card(MAIN_KEY)})), ["receiver"])
        short = {"lxmf": card(MAIN_KEY)["lxmf"], "key": "ab" * 10}
        self.assertEqual(self.fields(station_doc(receiver={"main": short, "backup": card(BACKUP_KEY)})), ["receiver.main.key"])

    def test_text_rule_matches_the_reference_model(self):
        samples = ["Szkoła", "Школа №2", "á", "á", 'a"b', "a\\b", "tab\there", "zw​sp", "line ",
                   "", "x" * 64, "x" * 65, "ż" * 32, "ż" * 33, "", "🙂", "\U000E0001"]
        for s in samples:
            try:
                reference._text(s, 64, 1)
                accepted = True
            except ValueError:
                accepted = False
            self.assertEqual(configdoc.text_problem(s, 64, 1) is None, accepted, repr(s))

    def test_normalize_cleans_what_the_form_types(self):
        doc = configdoc.normalize(station_doc(addresses=['  Hala "Orlik" á \\ B  '], ifac=" " + "AB" * 16 + " "))
        self.assertEqual(doc["addresses"], ["Hala „Orlik” á / B"])
        self.assertEqual(doc["ifac"], "ab" * 16)
        node = configdoc.normalize(station_doc(role="wezel"))
        self.assertEqual(set(node), {"role", "ifac", "radio"})
        self.assertEqual(configdoc.check(node), [])

    def test_encoding_has_no_escapes_and_respects_the_size(self):
        data = configdoc.encode(station_doc())
        self.assertNotIn(b"\\", data)
        self.assertIn("людина".encode(), data)
        self.assertEqual(json.loads(data), station_doc())
        biggest = station_doc(addresses=["ż" * 32] * 8, phrases=[["ż" * 48] * 3] * 11)
        self.assertEqual(configdoc.check(biggest), [])
        self.assertLessEqual(len(configdoc.encode(biggest)), configdoc.DOC_MAX)
        self.assertEqual(len(configdoc.new_ifac()), 32)


class FakePort:
    """In-memory port: `respond(message)` returns the lines the station writes back."""

    def __init__(self, respond, hello=True):
        self.respond, self.out, self.closed = respond, queue.Queue(), False
        if hello:
            self.push({"usb": 2, "seq": 1, "type": "hello", "contracts": [2], "name": "WICI-0A0B0C", "lxmf": "",
                       "role": "stacja", "prep": True, "configured": False})

    def push(self, message):
        self.out.put(json.dumps(message, ensure_ascii=False).encode() + b"\n")

    def read(self, timeout):
        if self.closed:
            raise serialport.PortClosed("closed")
        try:
            return self.out.get(timeout=timeout)
        except queue.Empty:
            return b""

    def write(self, data):
        self.assertions(data)
        for m in self.respond(json.loads(data)):
            self.push(m)

    def assertions(self, data):
        assert data.endswith(b"\n") and b"\\u" not in data and len(data) <= 1025

    def close(self):
        self.closed = True


class StationScript:
    """Station side of a transfer: keeps `configure` documents, answers `config_get`."""

    def __init__(self):
        self.doc, self.parts, self.seq = None, b"", 0

    def __call__(self, m):
        def reply(type_, **f):
            self.seq += 1
            return {"usb": 2, "seq": self.seq, "type": type_, "re": m["seq"], **f}
        t = m["type"]
        if t == "status":
            return [reply("status", prep=True)]
        if t == "xfer_begin" and m["op"] == "configure":
            self.parts, self.want = b"", (m["size"], m["sha256"])
            return [reply("ok", xfer="0000abcd", max_part=512)]
        if t == "xfer_part":
            assert m["offset"] == len(self.parts)
            self.parts += base64.b64decode(m["data"])
            return [reply("ok", next=len(self.parts))]
        if t == "xfer_commit" and self.parts is not None:
            if (len(self.parts), hashlib.sha256(self.parts).hexdigest()) != self.want:
                return [reply("rejected", reason="hash")]
            self.doc = self.parts
            return [reply("ok", config_seq=3, worst_request=212)]
        if t == "xfer_begin" and m["op"] == "config_get":
            self.parts = None
            return [reply("ok", xfer="0000abce", size=len(self.doc), sha256=hashlib.sha256(self.doc).hexdigest())]
        if t == "xfer_read":
            return [reply("data", offset=m["offset"],
                          data=base64.b64encode(self.doc[m["offset"]:m["offset"] + m["length"]]).decode())]
        if t == "silence":
            return [reply("pending", confirm_s=30), reply("ok")]
        if t == "card":
            return [reply("rejected", reason="prep_required")]
        return []


class LinkTest(unittest.TestCase):
    def test_encode_rejects_escapes_and_long_lines(self):
        self.assertEqual(usbproto.encode({"a": "ż"}), '{"a":"ż"}'.encode() + b"\n")
        with self.assertRaises(ValueError):
            usbproto.encode({"a": 'x"y'})
        with self.assertRaises(ValueError):
            usbproto.encode({"a": "x" * 1020})

    def test_requests_transfers_pending_and_rejections(self):
        script = StationScript()
        link = usbproto.Link(FakePort(script))
        self.assertEqual(link.wait_hello()["name"], "WICI-0A0B0C")
        self.assertTrue(link.request("status")["prep"])
        data = configdoc.encode(station_doc(addresses=["ż" * 32] * 8))
        self.assertGreater(len(data), 1024)
        self.assertEqual(link.write_transfer("configure", data)["config_seq"], 3)
        self.assertEqual(link.read_transfer("config_get"), data)
        seen = []
        self.assertEqual(link.request("silence", on_pending=seen.append, on=True)["type"], "ok")
        self.assertEqual(seen[0]["confirm_s"], 30)
        with self.assertRaises(usbproto.Rejected) as e:
            link.request("card")
        self.assertEqual(e.exception.reason, "prep_required")
        with self.assertRaises(usbproto.ProtocolError):
            link.request("unknown", timeout=0.3)
        link.close()

    def test_seq_rejection_is_retried_once_with_the_next_number(self):
        calls = []

        def respond(m):
            calls.append(m["seq"])
            kind = {"type": "rejected", "reason": "seq"} if len(calls) == 1 else {"type": "status"}
            return [{"usb": 2, "seq": len(calls), "re": m["seq"], **kind}]
        link = usbproto.Link(FakePort(respond))
        self.assertEqual(link.request("status")["type"], "status")
        self.assertEqual(calls, [1, 2])
        link.close()

    def test_second_seq_rejection_starts_a_new_session(self):
        link = usbproto.Link(FakePort(lambda m: [{"usb": 2, "seq": 9, "re": m["seq"], "type": "rejected", "reason": "seq"}]))
        with self.assertRaises(usbproto.ProtocolError):
            link.request("status")
        link.close()
        link.close()                                             # drugie zamknięcie niczego nie psuje
        self.assertFalse(link.thread.is_alive())                 # wątek odczytu zatrzymany przed zamknięciem portu
        with self.assertRaises(serialport.PortClosed):
            link.request("status")

    def test_closed_port_ends_waiting(self):
        port = FakePort(lambda m: [])
        link = usbproto.Link(port)
        threading.Timer(0.2, port.close).start()
        with self.assertRaises(serialport.PortClosed):
            link.request("status", timeout=5)

    def test_garbage_and_kiss_frames_are_ignored(self):
        port = FakePort(lambda m: [{"usb": 2, "seq": 2, "type": "status", "re": m["seq"]}], hello=False)
        port.out.put(b"\xc0\x00\x01\x02\xc0" * 2000)           # ramki KISS węzła: bez LF
        port.out.put(b"boot log line\r\n{not json}\n")
        link = usbproto.Link(port)
        self.assertEqual(link.request("status")["type"], "status")
        link.close()


class StationTest(unittest.TestCase):
    def test_silent_port_is_skipped_until_unplugged_or_rescan(self):
        opened, present = [], ["A", "B"]

        def open_port(name):
            opened.append(name)
            return FakePort(lambda m: [], hello=(name == "B" and len(opened) > 3))
        with unittest.mock.patch.object(serialport, "candidates", lambda: list(present)), \
                unittest.mock.patch.object(serialport, "open_port", open_port), \
                unittest.mock.patch.object(usbproto, "HELLO_WAIT", 0.1):
            st = usbproto.Station()
            st._connect()
            self.assertEqual((opened, st.state["skipped"]), (["A", "B"], ["A", "B"]))
            st._connect()
            self.assertEqual(opened, ["A", "B"])                 # bez ponownego otwierania (DTR)
            present.remove("A")
            st._connect()
            present.append("A")
            st._connect()
            self.assertEqual(opened, ["A", "B", "A"])            # odłączony i podłączony port znów sprawdzany
            st.rescan()
            st._connect()
            self.assertEqual(opened[3], "B")
            self.assertEqual((st.state["phase"], st.state["port"]), ("connected", "B"))
            st.stop()

    def test_operations_run_one_at_a_time(self):
        st = usbproto.Station()
        st.link = usbproto.Link(FakePort(lambda m: []))
        st.state = {**st.state, "phase": "connected"}
        active, overlap = [], []

        def op(link):
            active.append(1)
            overlap.append(len(active))
            time.sleep(0.1)
            active.pop()
        threads = [threading.Thread(target=st.call, args=(op,)) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(overlap, [1, 1, 1])
        st.stop()


class SerialPortTest(unittest.TestCase):
    def test_windows_structures_have_the_kernel32_layout(self):
        self.assertEqual(ctypes.sizeof(serialport.DCB), 28)
        self.assertEqual(ctypes.sizeof(serialport.COMMTIMEOUTS), 20)
        dcb = serialport.DCB()
        dcb.fDtrControl, dcb.fRtsControl, dcb.fBinary = 1, 1, 1
        flags = int.from_bytes(bytes(dcb)[8:12], "little")
        self.assertEqual(flags, 0x1 | (1 << 4) | (1 << 12))

    def test_missing_port_is_reported_as_missing(self):
        name = "COM250" if sys.platform == "win32" else "/dev/wici-no-such-port"
        with self.assertRaises(serialport.PortError) as e:
            serialport.open_port(name)
        self.assertEqual(e.exception.kind, "missing")
        self.assertIsInstance(serialport.candidates(), list)

    @unittest.skipIf(sys.platform == "win32", "POSIX pseudo-terminal")
    def test_posix_port_reads_and_writes_raw_bytes(self):
        import pty
        master, slave = pty.openpty()
        port = serialport.PosixPort(os.ttyname(slave))
        try:
            port.write(b'{"a":1}\r\n')
            self.assertEqual(os.read(master, 100), b'{"a":1}\r\n')   # bez OPOST: CR i LF bez zmian
            os.write(master, b"\x03\x11xyz\n")
            time.sleep(0.05)
            self.assertEqual(port.read(1), b"\x03\x11xyz\n")      # bez ISIG i IXON: bajty sterujące przechodzą
            self.assertEqual(port.read(0.05), b"")
        finally:
            port.close()
            os.close(master)
            os.close(slave)


class SysCryptoTest(unittest.TestCase):
    """System AES and PBKDF2 (CNG, CommonCrypto, libcrypto): known answers and the sealed copy format."""

    def test_selfcheck_fails_without_assert(self):
        with unittest.mock.patch.object(syscrypto, "aes_cbc", return_value=bytes(48)):
            with self.assertRaises(syscrypto.CryptoError):
                syscrypto.selfcheck()

    def test_known_answers_and_tampering(self):
        self.assertIn(syscrypto.selfcheck(), ("windows", "mac", "linux"))

    def test_pbkdf2_matches_hashlib(self):
        if not hasattr(hashlib, "pbkdf2_hmac"):
            self.skipTest("hashlib bez OpenSSL")
        self.assertEqual(syscrypto.pbkdf2(b"haslo z koperty", b"sol", 1000),
                         hashlib.pbkdf2_hmac("sha256", b"haslo z koperty", b"sol", 1000, 32))

    def test_sealed_copy_is_fresh_and_bound(self):
        key = bytes(range(32))
        data = bytes(range(256)) * 1000
        a, b = syscrypto.seal(key, data, b"gen 7"), syscrypto.seal(key, data, b"gen 7")
        self.assertNotEqual(a, b)                                 # losowy IV przy każdym zapisie
        self.assertEqual(syscrypto.open_(key, b, b"gen 7"), data)
        for broken in (a[:1 + 16] + bytes([a[17] ^ 1]) + a[18:], b"\x02" + a[1:], a[:40]):
            with self.assertRaises(syscrypto.CryptoError):
                syscrypto.open_(key, broken, b"gen 7")
        with self.assertRaises(syscrypto.CryptoError):
            syscrypto.open_(bytes(32), a, b"gen 7")


class DatabaseTest(unittest.TestCase):
    """Encrypted laptop database: accounts on the stick, snapshots on disk and stick, laptop swaps."""

    PASSWORDS = {"gospodarz": "las rzeka most okno chleb", "zastepca-1": "sowa dach pole kret lampa"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.usb, self.keys = root / "usb" / "kopia", root / "usb" / "keys"
        (root / "usb").mkdir()
        self.laptop = lambda name: root / name
        self.kit, self.key = database.Kit.create(self.keys, self.PASSWORDS, "zapasowe haslo szesc slow tutaj",
                                                 iterations=1000)

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, laptop="a", usb=True, **kw):
        return database.Database(self.key, self.laptop(laptop), self.usb if usb else None, self.kit.recovery(),
                                 store.SCHEMA, **kw)

    def add(self, db, detail):
        store.Journal(db).add("WICI-3FA21C", "", "test", True, detail)

    def details(self, db):
        return [r["detail"] for r in reversed(store.Journal(db).recent(5000))]

    def test_accounts_unlock_change_and_limit(self):
        self.assertEqual(self.kit.unlock("gospodarz", "  Las RZEKA most  okno chleb "), self.key)
        self.assertEqual(self.kit.unlock("zastepca-1", self.PASSWORDS["zastepca-1"]), self.key)
        self.kit.change_password("zastepca-1", self.PASSWORDS["zastepca-1"], "nowe haslo z koperty numer dwa",
                                 iterations=1000)
        self.assertEqual(self.kit.unlock("zastepca-1", "nowe haslo z koperty numer dwa"), self.key)
        self.assertEqual(self.kit.names(), ["gospodarz", "zastepca-1"])
        kit = database.Kit(self.keys)                       # inny laptop czyta te same pliki
        for _ in range(database.LOGIN_LIMIT):
            with self.assertRaises(database.LoginError):
                kit.unlock("gospodarz", "zle haslo")
        with self.assertRaisesRegex(database.LoginError, "Poczekaj"):
            kit.unlock("gospodarz", self.PASSWORDS["gospodarz"])   # limit także dla dobrego hasła
        with unittest.mock.patch.object(database.time, "monotonic", return_value=time.monotonic() + 61):
            self.assertEqual(kit.unlock("gospodarz", self.PASSWORDS["gospodarz"]), self.key)
        (self.keys / "zestaw.key").write_bytes(os.urandom(32))   # konta bez pliku zestawu nie otwierają klucza
        with self.assertRaises(database.LoginError):
            database.Kit(self.keys).unlock("gospodarz", self.PASSWORDS["gospodarz"])
        with self.assertRaises(database.StorageError):
            database.Kit.create(self.keys, self.PASSWORDS, "x")

    def test_no_plain_data_and_another_laptop_continues(self):
        db = self.open("a")
        self.add(db, "Szkoła nr 5, piwnica")
        db.flush()
        for f in list(self.laptop("a").iterdir()) + list(self.usb.iterdir()):
            self.assertNotIn("Szkoła".encode(), f.read_bytes(), f)
            self.assertNotIn(b"SQLite format", f.read_bytes(), f)
        self.assertTrue(db.status()["usb_saved"])
        db.close()
        other = self.open("b")                              # laptop A zniknął; B ma tylko pamięć USB
        self.assertEqual(self.details(other), ["Szkoła nr 5, piwnica"])
        self.add(other, "drugi wpis")
        other.hand_back()
        self.assertEqual(list(self.laptop("b").iterdir()), [])
        back = self.open("a")                               # A wraca ze starszą kopią na dysku: wygrywa pamięć
        self.assertEqual(self.details(back), ["Szkoła nr 5, piwnica", "drugi wpis"])
        back.close()

    def test_newer_disk_copy_wins_and_heals_the_stick(self):
        db = self.open("a")
        self.add(db, "1")
        db.flush()
        db.close()
        db = self.open("a", usb=False)                      # pamięć wyjęta: zmiana tylko na dysku
        self.add(db, "2")
        db.close()
        db = self.open("a")
        self.assertEqual(self.details(db), ["1", "2"])
        db.flush()                                          # pamięć dostaje nowszą kopię bez nowej zmiany
        db.close()
        db = self.open("c")
        self.assertEqual(self.details(db), ["1", "2"])
        db.close()

    def test_diverged_copies_are_a_conflict(self):
        db = self.open("a")
        self.add(db, "wspólny")
        db.close()
        a = self.open("a", usb=False)
        self.add(a, "tylko A")
        a.close()
        b = self.open("b")
        self.add(b, "tylko B")
        b.close()
        with self.assertRaises(database.Conflict) as cm:
            self.open("a")
        self.assertEqual({cm.exception.disk.place, cm.exception.usb.place}, {"disk", "usb"})
        db = self.open("a", prefer="usb")
        self.assertEqual(self.details(db), ["wspólny", "tylko B"])
        self.add(db, "po wyborze")
        db.close()
        self.assertEqual(len(list(self.usb.parent.glob("kopia/konflikt-disk-*"))), 1)   # odrzucona zostaje
        db = self.open("a")                                 # stare pliki A nie wracają jako nowsze
        self.assertEqual(self.details(db), ["wspólny", "tylko B", "po wyborze"])
        db.close()

    def test_conflict_choice_holds_without_further_changes(self):
        db = self.open("a")
        self.add(db, "wspólny")
        db.close()
        a = self.open("a", usb=False)
        for i in range(3):
            self.add(a, f"A{i}")                            # A ma wyższe pokolenie niż B
        a.close()
        b = self.open("b")
        self.add(b, "B")
        b.close()
        self.open("a", prefer="usb").close()                # wybór bez nowej zmiany
        db = self.open("a")
        self.assertEqual(self.details(db), ["wspólny", "B"])
        db.close()

    def test_recovery_slot_follows_the_account_file(self):
        db = self.open("a")
        self.add(db, "x")
        db.close()
        slot = database._slot(self.key, "nowe haslo odtworzenia", database.RECOVERY_AAD, 1000)
        db = database.Database(self.key, self.laptop("a"), self.usb, slot, store.SCHEMA)
        self.add(db, "y")
        db.close()
        self.assertEqual(database.key_from_recovery([self.usb], "nowe haslo odtworzenia"), self.key)

    def test_removed_stick_is_not_recreated_on_the_disk(self):
        stick = Path(self.tmp.name) / "Volumes" / "WICI"
        stick.mkdir(parents=True)
        db = database.Database(self.key, self.laptop("a"), stick / "kopia", None, store.SCHEMA)
        self.add(db, "x")
        db.flush()
        shutil.rmtree(stick)                                # pamięć wyjęta
        self.add(db, "y")
        deadline = time.monotonic() + 5
        while db.status()["usb_error"] is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(db.status()["usb_error"])
        self.assertFalse(stick.exists())
        with self.assertRaises(database.StorageError):
            db.flush(timeout=0.5)
        with self.assertRaises(database.StorageError):
            db.close(timeout=0.5)

    def test_torn_write_and_tampering_fall_back(self):
        db = self.open("a", usb=False)
        for i in range(3):
            self.add(db, str(i))
        db.close()
        newest = max(self.laptop("a").iterdir(), key=lambda f: database._read(f, self.key, "disk").gen)
        raw = newest.read_bytes()
        newest.write_bytes(raw[:len(raw) // 2])             # przerwany zapis
        db = self.open("a", usb=False)
        self.assertEqual(self.details(db), ["0", "1"])
        db.close()
        head, header, sealed = database._split(raw)
        header["gen"] += 100                                # podbite pokolenie bez klucza: MAC się nie zgadza
        text = json.dumps(header).encode()
        newest.write_bytes(database.MAGIC + len(text).to_bytes(4, "big") + text + sealed)
        db = self.open("a", usb=False)
        self.assertEqual(self.details(db), ["0", "1"])
        db.close()

    def test_recovery_password_without_account_file(self):
        db = self.open("a")
        self.add(db, "x")
        db.hand_back()
        for f in self.keys.iterdir():
            f.unlink()
        with self.assertRaises(database.LoginError):
            database.key_from_recovery([self.usb], "zle")
        key = database.key_from_recovery([self.usb], "Zapasowe haslo szesc slow tutaj")
        self.assertEqual(key, self.key)

    def test_concurrent_writes_are_coalesced_and_fast(self):
        db = self.open("a")
        db.write(lambda c: c.executemany("INSERT INTO journal (at, station, lxmf, op, ok, detail) "
                                         "VALUES ('t','WICI-1','','x',1,?)", [("x" * 300,)] * 1000))
        writes, latency = [], []
        real = database._write_durable

        def counting(path, data):
            writes.append(path.parent.name)
            real(path, data)

        def phone(n):
            for i in range(10):
                t = time.monotonic()
                self.add(db, f"{n}-{i}")
                latency.append(time.monotonic() - t)

        with unittest.mock.patch.object(database, "_write_durable", counting):
            threads = [threading.Thread(target=phone, args=(n,)) for n in range(15)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            db.flush()
        self.assertEqual(len(self.details(db)), 1150)
        self.assertLess(writes.count("a"), 150)             # migawki łączone, nie jedna na zmianę
        self.assertLess(max(latency), 1.0, f"max {max(latency):.3f} s, {writes.count('a')} zapisów")
        db.close()

    def test_disk_error_is_reported_to_the_writer(self):
        db = self.open("a", usb=False)
        with unittest.mock.patch.object(database, "_write_durable", side_effect=OSError("dysk pełny")):
            with self.assertRaisesRegex(database.StorageError, "dysk pełny"):
                self.add(db, "x")
            self.assertEqual(db.status()["disk_error"], "dysk pełny")
        db.flush()                                          # ponowna próba po usunięciu przyczyny
        self.assertIsNone(db.status()["disk_error"])
        db.close()

    def test_destroy_removes_copies_and_accounts(self):
        db = self.open("a")
        self.add(db, "x")
        db.flush()
        db.destroy(self.keys)
        self.assertEqual(list(self.laptop("a").iterdir()), [])
        self.assertEqual(list(self.usb.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])
        with self.assertRaises(database.LoginError):
            database.key_from_recovery([self.usb], "zapasowe haslo szesc slow tutaj")

    def test_hand_back_needs_the_stick(self):
        db = self.open("a", usb=False)
        self.add(db, "x")
        with self.assertRaises(database.StorageError):
            db.hand_back()
        self.assertTrue(any(self.laptop("a").iterdir()))   # bez pamięci dysk zostaje nietknięty
        db.close()


class PasswordsTest(unittest.TestCase):
    def test_word_list(self):
        from wici import passwords
        words = passwords.words()
        self.assertEqual(len(words), 4096)
        self.assertEqual(words, sorted(words))
        self.assertTrue(all(set(w) <= set("abcdefghijklmnoprstuwyz") for w in words))   # bez polskich liter
        for bad in ("kurwa", "trup", "pomocy", "wici", "szwaby", "omg"):
            self.assertNotIn(bad, words)
        pw = passwords.generate()
        self.assertEqual(len(pw.split()), 5)
        self.assertTrue(all(w in words for w in pw.split()))
        self.assertEqual(len(passwords.recovery().split()), 6)
        self.assertEqual(database.normalize_password(pw.upper()), pw.encode())

    def test_excluded_words_are_not_on_the_list(self):
        from wici import passwords
        text = (LAPTOP / "build" / "slowa" / "wykluczone.txt").read_text(encoding="utf-8")
        items = {i for line in text.splitlines() for i in line.split("#", 1)[0].split()}
        kept = set(passwords.words())
        self.assertEqual([i for i in items if not i.endswith("*") and i in kept], [])
        self.assertEqual([w for w in kept if w.startswith(tuple(i[:-1] for i in items if i.endswith("*")))], [])


class SessionTest(unittest.TestCase):
    """Kit on the stick, login and the database behind the panel."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "usb").mkdir()

    def session(self, laptop="a"):
        s = session.Session(self.root / "usb", self.root / laptop, iterations=1000)
        self.addCleanup(s.close)
        return s

    def test_new_kit_envelopes_and_login_on_another_laptop(self):
        a = self.session("a")
        self.assertEqual(a.describe()["kit"], "new")
        envelopes = a.create(2)["envelopes"]
        self.assertEqual([(e["no"], e["account"]) for e in envelopes],
                         [(1, "gospodarz"), (2, "zastepca-1"), (3, "zastepca-2"), (4, "odtworzenie")])
        self.assertEqual([len(e["password"].split()) for e in envelopes], [5, 5, 5, 6])
        self.assertEqual(a.describe()["user"], "gospodarz")
        a.add("WICI-3FA21C", "", "configure", True, "config_seq 1")
        a.close()
        b = self.session("b")                             # inny laptop, ta sama pamięć
        state = b.describe()
        self.assertEqual((state["kit"], [x["label"] for x in state["accounts"]]),
                         ("ready", ["Gospodarz", "Zastępca 1", "Zastępca 2"]))
        with self.assertRaises(session.NotLoggedIn):
            b.add("WICI-3FA21C", "", "card", True)
        self.assertEqual(b.recent(), [])
        with self.assertRaises(database.LoginError):
            b.login("zastepca-1", envelopes[0]["password"])
        b.login("zastepca-1", envelopes[1]["password"].upper())
        self.assertEqual([e["op"] for e in b.recent()], ["login", "configure", "kit_create", "login"])

    def test_new_password_logout_and_hand_back(self):
        a = self.session("a")
        envelopes = a.create(1)["envelopes"]
        new = a.new_password("zastepca-1")["envelopes"][0]["password"]
        a.logout()
        with self.assertRaises(database.LoginError):
            a.login("zastepca-1", envelopes[1]["password"])  # stare hasło z otwartej koperty już nie działa
        a.login("zastepca-1", new)
        (self.root / "a" / "dziennik.sqlite").write_bytes(b"etap 1")
        a.hand_back()
        self.assertEqual(list((self.root / "a" / "baza").iterdir()), [])
        self.assertFalse((self.root / "a" / "dziennik.sqlite").exists())
        self.assertEqual(a.describe()["kit"], "ready")
        b = self.session("b")
        b.login("gospodarz", envelopes[0]["password"])
        self.assertIn("hand_back", [e["op"] for e in b.recent()])

    def test_conflict_choice(self):
        a = self.session("a")
        envelopes = a.create(0)["envelopes"]
        a.close()
        pw = envelopes[0]["password"]
        off = session.Session(self.root / "bez-pamieci", self.root / "a", iterations=1000)   # pamięci nie ma
        off.kit = database.Kit(self.root / "usb" / "keys")      # konta z pamięci, kopia bez niej
        off.login("gospodarz", pw)
        off.add("", "", "tylko na dysku A", True)
        with self.assertRaises(database.StorageError):      # pamięci nie ma: zmiana zostaje tylko na dysku A
            off.db.close(timeout=0.5)
        off.db = None
        b = self.session("b")
        b.login("gospodarz", pw)
        b.add("", "", "tylko na B", True)
        b.close()
        a = self.session("a")
        with self.assertRaises(database.Conflict):
            a.login("gospodarz", pw)
        self.assertEqual(set(a.describe()["conflict"]), {"disk", "usb"})
        a.choose("usb")
        self.assertIsNone(a.describe()["conflict"])
        ops = [e["op"] for e in a.recent()]
        self.assertIn("tylko na B", ops)
        self.assertNotIn("tylko na dysku A", ops)

    def test_recovery_without_account_file(self):
        a = self.session("a")
        envelopes = a.create(1)["envelopes"]
        a.add("WICI-3FA21C", "", "configure", True)
        a.hand_back()
        (self.root / "usb" / "keys" / "konta.json").write_text("uszkodzony")
        b = self.session("b")
        self.assertEqual(b.describe()["kit"], "broken")
        with self.assertRaises(database.LoginError):
            b.recover("zle haslo")
        fresh = b.recover(envelopes[-1]["password"], 1)["envelopes"]
        self.assertEqual([e["account"] for e in fresh], ["gospodarz", "zastepca-1", "odtworzenie"])
        self.assertIn("configure", [e["op"] for e in b.recent()])
        b.logout()
        b.login("gospodarz", fresh[0]["password"])
        with self.assertRaises(database.StorageError):
            b.recover(fresh[-1]["password"])                # plik kont jest cały

    def test_removed_stick(self):
        a = self.session("a")
        a.create(1)
        stick = self.root / "usb"
        moved = self.root / "usb-wyjeta"
        a.db.flush()                                        # Windows: nie przenosi katalogu z otwartym plikiem
        stick.rename(moved)                                 # pamięć wyjęta przy zalogowanym panelu
        state = a.describe()
        self.assertEqual((state["kit"], [x["id"] for x in state["accounts"]]), ("open", ["gospodarz", "zastepca-1"]))
        with self.assertRaises(database.StorageError):
            a.hand_back()                                   # od razu, bez czekania na zapis
        self.assertTrue(any((self.root / "a" / "baza").iterdir()))
        moved.rename(stick)
        a.close()
        stick.rename(moved)
        b = self.session("b")
        self.assertEqual(b.describe()["kit"], "missing")
        with self.assertRaises(database.StorageError):
            b.create(1)
        self.assertFalse(stick.exists())                    # nie powstał katalog w miejscu pamięci

    def test_stick_back_under_another_path(self):
        a = self.session("a")
        pw = a.create(0)["envelopes"][0]["password"]
        stick, moved = self.root / "usb", self.root / "usb-e"
        a.db.flush()
        stick.rename(moved)                                 # wypadła i wróciła pod inną literą dysku
        stick.mkdir()                                       # a starą literę zajęła inna pamięć
        a.add("WICI-3FA21C", "", "configure", True, "bez pamięci")
        with self.assertRaises(database.StorageError):
            a.hand_back()
        self.assertFalse(a.adopt(self.root / "nie-ma"))
        self.assertTrue(a.adopt(moved))
        self.assertEqual(a.describe()["usb"], str(moved))
        a.db.flush(timeout=5)                               # zmiana sprzed przełączenia jest już na pamięci
        self.assertEqual(list(stick.iterdir()), [])         # na obcej pamięci nic nie powstało
        a.hand_back()
        self.assertFalse(any((self.root / "a" / "baza").iterdir()))
        b = session.Session(moved, self.root / "b", iterations=1000)
        self.addCleanup(b.close)
        b.login("gospodarz", pw)
        self.assertEqual([e["op"] for e in b.recent()][:4], ["login", "hand_back", "usb_moved", "configure"])

    def test_stick_is_not_adopted_when_it_moved_on(self):
        a = self.session("a")
        envelopes = a.create(0)["envelopes"]
        stick, moved = self.root / "usb", self.root / "usb-e"
        a.db.flush()
        stick.rename(moved)
        b = session.Session(moved, self.root / "b", iterations=1000)   # w międzyczasie praca na innym laptopie
        self.addCleanup(b.close)
        b.login("gospodarz", envelopes[0]["password"])
        b.hand_back()
        self.assertFalse(a.adopt(moved))
        other = self.root / "inny"
        other.mkdir()
        c = session.Session(other, self.root / "c", iterations=1000)
        self.addCleanup(c.close)
        c.create(0)                                         # inny zestaw
        self.assertFalse(a.adopt(other))
        self.assertEqual(a.describe()["usb"], str(stick))
        moved.rename(stick)
        self.assertFalse(a.adopt(moved))                    # stara ścieżka znów jest: nic do przełączania

    def test_destroy(self):
        a = self.session("a")
        envelopes = a.create(1)["envelopes"]
        (self.root / "a" / "dziennik.sqlite").write_bytes(b"etap 1")
        self.assertEqual(a.destroy(), {"usb": True})
        self.assertEqual(a.describe()["kit"], "destroyed")
        for d in (self.root / "usb" / "keys", self.root / "usb" / "kopia", self.root / "a" / "baza"):
            self.assertEqual(list(d.iterdir()), [], d)
        self.assertFalse((self.root / "a" / "dziennik.sqlite").exists())
        with self.assertRaises(database.StorageError):
            a.create(1)                                     # do ponownego uruchomienia nic nie powstaje
        with self.assertRaises(database.StorageError):
            a.login("gospodarz", envelopes[0]["password"])
        prep = unittest.mock.Mock()
        with self.assertRaises(session.NotLoggedIn):
            web.destroy(Panel(None, prep, a, "tok", {}), {"confirm": "ZNISZCZ"})
        prep.destroy_station.assert_not_called()           # bez zalogowania stacja nie dostaje polecenia
        self.assertEqual(self.session("b").describe()["kit"], "new")

    def test_destroy_reports_a_copy_still_being_written(self):
        a = self.session("a")
        a.create(0)
        a.db.flush()
        stuck = threading.Thread(target=time.sleep, args=(10,), daemon=True, name="wici-kopia-usb")
        stuck.start()
        a.db.threads.append(stuck)                          # zapis na pamięci USB, który utknął
        with unittest.mock.patch.object(stuck, "join"):
            with self.assertRaises(database.StorageError) as e:
                a.destroy()
        self.assertIn("zapis kopii w toku (wici-kopia-usb)", str(e.exception))
        self.assertEqual(a.describe()["kit"], "destroyed")
        self.assertEqual(list((self.root / "usb" / "keys").iterdir()), [])

    def test_destroy_without_stick(self):
        a = self.session("a")
        a.create(0)
        a.db.flush()
        moved = self.root / "usb-wyjeta"
        (self.root / "usb").rename(moved)
        self.assertEqual(a.destroy(), {"usb": False})
        self.assertEqual(list((self.root / "a" / "baza").iterdir()), [])
        self.assertTrue(any((moved / "keys").iterdir()))     # zostaje: pamięć niszczy się fizycznie

    def test_second_login_and_recovery_limit(self):
        a = self.session("a")
        envelopes = a.create(0)["envelopes"]
        with self.assertRaises(database.StorageError):
            a.login("gospodarz", envelopes[0]["password"])  # druga baza na tych samych plikach
        a.hand_back()
        (self.root / "usb" / "keys" / "konta.json").unlink()
        b = self.session("b")
        for _ in range(database.LOGIN_LIMIT):
            with self.assertRaises(database.LoginError):
                b.recover("zle")
        with self.assertRaisesRegex(database.LoginError, "Poczekaj"):
            b.recover(envelopes[-1]["password"])

    def test_usb_root(self):
        with unittest.mock.patch.dict(os.environ, {"WICI_USB": ""}), \
                unittest.mock.patch.object(sys, "argv", [str(self.root / "E" / "app" / "wici.pyz")]):
            self.assertEqual(session.usb_root(), (self.root / "E").resolve())
        with unittest.mock.patch.dict(os.environ, {"WICI_USB": str(self.root / "U")}):
            self.assertEqual(session.usb_root(), self.root / "U")
        with unittest.mock.patch.dict(os.environ, {"WICI_USB": ""}), \
                unittest.mock.patch.object(sys, "argv", ["-m"]):
            self.assertIsNone(session.usb_root())


def memory_journal(tmp):
    """Journal in an encrypted database with a random key, without a stick (tests of other parts)."""
    return store.Journal(database.Database(os.urandom(32), Path(tmp) / "baza", None, None, store.SCHEMA))


class JournalTest(unittest.TestCase):
    def test_append_only(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            j = memory_journal(tmp)
            j.add("WICI-1", "ab" * 16, "configure", True, "config_seq 1")
            j.add("WICI-1", "ab" * 16, "card", False, "prep_required")
            self.assertEqual([e["op"] for e in j.recent()], ["card", "configure"])
            for sql in ("DELETE FROM journal", "UPDATE journal SET ok=1"):
                with self.assertRaises(sqlite3.DatabaseError):
                    j.db.write(lambda c, sql=sql: c.execute(sql))
            j.close()

    def test_state_dir_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("WICI_STATE")
            os.environ["WICI_STATE"] = str(Path(tmp) / "stan")
            try:
                self.assertEqual(store.state_dir(), Path(tmp) / "stan")
                self.assertTrue((Path(tmp) / "stan").is_dir())
            finally:
                if old is None:
                    del os.environ["WICI_STATE"]
                else:
                    os.environ["WICI_STATE"] = old


class FakeStation:
    def __init__(self):
        self.state = {"phase": "searching", "port": None, "hello": None, "status": None, "problem": None}

    def call(self, fn):
        raise usbproto.ProtocolError("not connected")


class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        (Path(cls.tmp.name) / "usb").mkdir()
        cls.session = session.Session(Path(cls.tmp.name) / "usb", Path(cls.tmp.name) / "stan", iterations=1000)
        cls.envelopes = cls.session.create(1)["envelopes"]
        station = FakeStation()
        cls.panel = Panel(station, Prep(station, cls.session), cls.session, "tok-123", {"version": "t"})
        cls.server = serve(cls.panel, 0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.session.close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r, data

    def cookie(self):
        r, _ = self.request("GET", f"/start?t={self.panel.ticket()}")
        self.assertEqual(r.status, 303)
        self.assertIn("HttpOnly", r.getheader("Set-Cookie"))
        self.assertIn("SameSite=Strict", r.getheader("Set-Cookie"))
        return r.getheader("Set-Cookie").split(";")[0]

    def test_token_cookie_and_static_files(self):
        self.assertEqual(self.request("GET", "/start?t=wrong")[0].status, 403)
        self.assertEqual(self.request("GET", "/")[0].status, 403)
        c = self.cookie()
        r, page = self.request("GET", "/", headers={"Cookie": c})
        self.assertEqual(r.status, 200)
        self.assertIn(b"Przygotowanie stacji", page)
        self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        for path in ("/app.js", "/app.css", "/logo.svg", "/logo-dark.svg"):
            self.assertEqual(self.request("GET", path, headers={"Cookie": c})[0].status, 200, path)
        r, body = self.request("GET", "/api/state?v=-1", headers={"Cookie": c})
        self.assertEqual(json.loads(body)["station"]["phase"], "searching")

    def test_start_link_works_once_and_second_start_gets_a_new_one(self):
        self.assertEqual(self.request("GET", "/start?t=tok-123")[0].status, 403)   # sam token panelu nie otwiera
        ticket = self.panel.ticket()
        self.assertEqual(self.request("GET", f"/start?t={ticket}")[0].status, 303)
        self.assertEqual(self.request("GET", f"/start?t={ticket}")[0].status, 403)
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "instance.json"
            wici_main.write_instance(inst, self.port, "tok-123")
            url = wici_main.running_instance(inst, Path(tmp) / "pamiec")   # drugi START podaje swoją pamięć USB
            self.assertEqual(self.session.usb, Path(self.tmp.name) / "usb")    # obecna jest na miejscu
            self.assertTrue(url.startswith(f"http://127.0.0.1:{self.port}/start?t="))
            self.assertEqual(self.request("GET", urlsplit(url)._replace(scheme="", netloc="").geturl())[0].status, 303)
            wici_main.write_instance(inst, self.port, "wrong")
            self.assertIsNone(wici_main.running_instance(inst))

    def test_station_operations_need_login(self):
        c = {"Cookie": self.cookie(), "Content-Type": "application/json"}
        try:
            self.session.logout()
            state = json.loads(self.request("GET", "/api/state?v=-1", headers={"Cookie": c["Cookie"]})[1])
            self.assertEqual((state["session"]["kit"], state["journal"]), ("ready", []))
            for path in ("/api/config/read", "/api/config/write", "/api/card", "/api/hand-back", "/api/destroy"):
                r, body = self.request("POST", path, "{}", c)
                self.assertEqual((r.status, json.loads(body)["code"]), (401, "login"), path)
            self.assertEqual(self.request("POST", "/api/config/check", "{}", c)[0].status, 200)   # bez stacji i dziennika
            r, body = self.request("POST", "/api/login", json.dumps({"account": "gospodarz", "password": "zle"}), c)
            self.assertEqual((r.status, json.loads(body)["code"]), (401, "password"))
            r, body = self.request("POST", "/api/kit/create", json.dumps({"deputies": 1}), c)
            self.assertEqual((r.status, json.loads(body)["code"]), (409, "storage"))   # zestaw już jest
            self.assertEqual(json.loads(body)["error"], "Ta pamięć ma już konta zestawu.")
        finally:
            body = json.dumps({"account": "gospodarz", "password": self.envelopes[0]["password"]})
            self.assertEqual(self.request("POST", "/api/login", body, c)[0].status, 200)
        state = json.loads(self.request("GET", "/api/state?v=-1", headers={"Cookie": c["Cookie"]})[1])
        self.assertEqual(state["session"]["user"], "gospodarz")
        self.assertEqual(state["journal"][0]["op"], "login")

    def test_foreign_host_origin_and_content_type_are_refused(self):
        c = self.cookie()
        self.assertEqual(self.request("GET", "/", headers={"Cookie": c}, host="evil.example:80")[0].status, 403)
        body = json.dumps({"doc": station_doc()})
        ok = {"Cookie": c, "Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/api/config/check", body, ok)[0].status, 200)
        self.assertEqual(self.request("POST", "/api/config/check", body, {"Content-Type": "application/json"})[0].status, 403)
        self.assertEqual(self.request("POST", "/api/config/check", body, {**ok, "Origin": "http://evil.example"})[0].status, 403)
        self.assertEqual(self.request("POST", "/api/config/check", body, {**ok, "Content-Type": "text/plain"})[0].status, 415)
        self.assertEqual(self.request("POST", "/api/config/check", "x" * 70000, ok)[0].status, 413)
        self.assertEqual(self.request("POST", "/api/nothing", "{}", ok)[0].status, 404)

    def test_check_and_operations_without_station(self):
        c = {"Cookie": self.cookie(), "Content-Type": "application/json"}
        r, body = self.request("POST", "/api/config/check", json.dumps({"doc": station_doc(stations=0)}), c)
        self.assertEqual([p["field"] for p in json.loads(body)["problems"]], ["stations"])
        r, body = self.request("POST", "/api/config/write", json.dumps({"doc": station_doc()}), c)
        self.assertEqual(r.status, 409)
        self.assertIn("Brak odpowiedzi stacji", json.loads(body)["error"])
        self.assertFalse(self.session.recent()[0]["ok"])

    def test_unexpected_error_still_answers(self):
        c = {"Cookie": self.cookie(), "Content-Type": "application/json"}
        with unittest.mock.patch.object(self.panel.prep, "read_config", side_effect=KeyError("xfer")):
            r, body = self.request("POST", "/api/config/read", "{}", c)
        self.assertEqual(r.status, 500)
        self.assertEqual(json.loads(body)["code"], "KeyError")
        r, _ = self.request("POST", "/api/config/check", "{}", {"Content-Type": "application/json"})
        self.assertEqual((r.status, r.getheader("Connection")), (403, "close"))   # treść nieczytana: koniec połączenia


class PackageTest(unittest.TestCase):
    PACKAGE = LAPTOP / "wici"

    def test_logos_are_the_project_logo(self):
        ui = self.PACKAGE / "ui"
        self.assertEqual((ui / "logo.svg").read_bytes(), (ROOT / "media" / "logo" / "WICI-na-jasnym.svg").read_bytes())
        self.assertEqual((ui / "logo-dark.svg").read_bytes(), (ROOT / "media" / "logo" / "WICI-na-ciemnym.svg").read_bytes())

    def test_code_size_budget_and_python_version(self):
        files = [p for p in self.PACKAGE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        words = self.PACKAGE / "slowa.txt"                  # dane, nie kod: osobny limit
        total = sum(p.stat().st_size for p in files if p != words)
        self.assertLess(total, 256 * 1024, f"aplikacja ma {total} B; budżet etapu 2 to 256 KiB")
        self.assertLess(words.stat().st_size, 32 * 1024)
        for p in files:
            if p.suffix == ".py":
                ast.parse(p.read_text(encoding="utf-8"), feature_version=(3, 12))   # najstarszy Python w CI

    def test_only_the_standard_library(self):
        allowed = set(sys.stdlib_module_names) | {"wici"}
        for p in self.PACKAGE.rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
                for name in names:
                    self.assertIn(name.split(".")[0], allowed, f"{p.name}: {name}")

    def test_selftest_runs(self):
        out = subprocess.run([sys.executable, "-m", "wici", "--selftest"], cwd=LAPTOP, capture_output=True, text=True,
                             timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("selftest ok", out.stdout)


sys.path.insert(0, str(LAPTOP / "build"))
import build_usb  # noqa: E402


def tar_add(tar, name, data, mode=0o644):
    import tarfile
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(data), mode
    tar.addfile(info, __import__("io").BytesIO(data))


class BuildPinsTest(unittest.TestCase):
    def test_runtimes_are_pinned_with_hashes(self):
        pins = json.loads((LAPTOP / "build" / "runtimes.json").read_text(encoding="utf-8"))
        self.assertEqual(set(pins["runtimes"]), {"windows-amd64", "macos-arm64", "macos-x86_64", "linux-x86_64"})
        for name, pin in pins["runtimes"].items():
            self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$", name)
            self.assertTrue(pin["url"].startswith("https://"), name)
            self.assertIn(pins["python"].replace("+", "%2B"), pin["url"], name)

    def test_launchers_point_at_the_same_layout(self):
        mac = (LAPTOP / "build" / "launcher" / "start-mac.sh").read_text(encoding="utf-8")
        linux = (LAPTOP / "build" / "launcher" / "start-linux.sh").read_text(encoding="utf-8")
        win = (LAPTOP / "build" / "launcher" / "start-windows.c").read_text(encoding="utf-8")
        minor = build_usb.MINOR
        self.assertIn(f"/bin/python{minor}", mac)
        self.assertIn(f"runtime/linux-x86_64/bin/python{minor}", linux)
        self.assertIn(build_usb.STDLIB_ZIP, linux)
        self.assertIn("runtime\\\\windows\\\\pythonw.exe", win)
        for text in (mac, linux, win):
            self.assertIn("app", text)
            self.assertIn("wici.pyz", text)


@unittest.skipUnless(sys.version_info[:2] == tuple(map(int, build_usb.MINOR.split("."))),
                     f"bytecode of the USB tree needs Python {build_usb.MINOR}")
class BuildTreeTest(unittest.TestCase):
    """build_usb on archives shaped like the pinned ones, with the standard library of this Python."""

    def test_tree_layout_pruning_and_manifest(self):
        import sysconfig
        import tarfile
        import zipfile
        minor, tag = build_usb.MINOR, build_usb.TAG
        stdlib = Path(sysconfig.get_paths()["stdlib"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pbs = tmp / "pbs.tar.gz"
            with tarfile.open(pbs, "w:gz") as tar:
                tar_add(tar, f"python/bin/python{minor}", b"#!/bin/sh\n", 0o755)
                tar_add(tar, f"python/lib/libpython{minor}.dylib", b"lib")
                tar_add(tar, f"python/lib/python{minor}/lib-dynload/_ctypes.cpython-{tag}-darwin.so", b"so")
                tar_add(tar, f"python/lib/python{minor}/lib-dynload/_tkinter.cpython-{tag}-darwin.so", b"tk")
                tar_add(tar, "python/lib/tcl8.6/init.tcl", b"tcl")
                tar_add(tar, f"python/include/python{minor}/Python.h", b"h")
                tar_add(tar, f"python/lib/python{minor}/LICENSE.txt", b"PSF")
                for p in stdlib.rglob("*.py"):
                    rel = p.relative_to(stdlib).as_posix()
                    if "site-packages" not in rel:
                        tar_add(tar, f"python/lib/python{minor}/{rel}", p.read_bytes())
            emb = tmp / "embed.zip"
            with zipfile.ZipFile(emb, "w") as z:
                for name in ("python.exe", "pythonw.exe", f"python{tag}.dll", "_ctypes.pyd", "_ssl.pyd", "libssl-3.dll", "_hashlib.pyd", "libcrypto-3.dll",
                             f"python{tag}.zip", "LICENSE.txt", "sqlite3.dll"):
                    z.writestr(name, name)
            exe = tmp / "START-WINDOWS.exe"
            exe.write_bytes(b"MZ")
            out = tmp / "usb"
            archives = {"linux-x86_64": pbs, "macos-arm64": pbs, "windows-amd64": emb}
            with unittest.mock.patch("sys.stdout", new=__import__("io").StringIO()):
                doc = build_usb.build(out, ["linux-x86_64", "macos-arm64", "windows-amd64"], str(exe), archives)
            files = set(doc["files"])
            self.assertIn(f"runtime/{build_usb.STDLIB_ZIP}", files)
            self.assertIn(f"runtime/linux-x86_64/bin/python{minor}", files)
            self.assertIn(f"runtime/linux-x86_64/lib-dynload/_ctypes.cpython-{tag}-darwin.so", files)
            self.assertFalse([f for f in files if "tkinter" in f or "tcl" in f or "include/" in f or "_ssl" in f
                              or "libssl" in f or "libcrypto" in f or "_hashlib" in f or "libpython" in f
                              or f.endswith(f"windows/python{tag}.zip")], files)
            self.assertEqual((out / f"runtime/linux-x86_64/bin/python{minor}._pth").read_text(),
                             f"../../{build_usb.STDLIB_ZIP}\n../lib-dynload\n")
            self.assertEqual((out / f"runtime/windows/python{tag}._pth").read_bytes(),
                             f"..\\{build_usb.STDLIB_ZIP}\r\n.\r\n".encode())
            self.assertTrue(os.access(out / "START-MAC.app/Contents/MacOS/START", os.X_OK))
            self.assertTrue(os.access(out / "START-LINUX.sh", os.X_OK))
            for name in ("START-WINDOWS.exe", "INSTRUKCJA.html", "app/wici.pyz", "licenses/python-windows.txt",
                         "licenses/WICI-MIT.txt", "licenses/python-kod-wbudowany.txt", "sources/README.txt",
                         "START-MAC.app/Contents/Info.plist"):
                self.assertIn(name, files)
            with zipfile.ZipFile(out / "runtime" / build_usb.STDLIB_ZIP) as z:
                names = set(z.namelist())
            for needed in ("json/__init__.pyc", "http/server.pyc", "sqlite3/__init__.pyc", "ctypes/_layout.pyc",
                           "encodings/idna.pyc", "stringprep.pyc", "runpy.pyc", "ntpath.pyc", "webbrowser.pyc"):
                self.assertIn(needed, names)
            for unneeded in ("tkinter/__init__.pyc", "unittest/__init__.pyc", "asyncio/__init__.pyc", "pydoc.pyc"):
                self.assertNotIn(unneeded, names)
            self.assertLess((out / "runtime" / build_usb.STDLIB_ZIP).stat().st_size, 3 * 1024 * 1024)
            libs = (out / "licenses" / "python-biblioteki.txt").read_text(encoding="utf-8")
            for lib in ("LICENSE.openssl-3.txt", "LICENSE.libffi.txt", "LICENSE.sqlite.txt", "LICENSE.zstd.txt"):
                self.assertIn(lib, libs)
            self.assertIn("SipHash24", (out / "licenses" / "python-kod-wbudowany.txt").read_text(encoding="utf-8"))
            out2 = subprocess.run([sys.executable, str(out / "app" / "wici.pyz"), "--selftest"], capture_output=True,
                                  text=True, timeout=60)
            self.assertEqual(out2.returncode, 0, out2.stdout + out2.stderr)
            first = (out / "runtime" / build_usb.STDLIB_ZIP).read_bytes()
            with unittest.mock.patch("sys.stdout", new=__import__("io").StringIO()):
                build_usb.build(out, ["linux-x86_64", "macos-arm64", "windows-amd64"], str(exe), archives)
            self.assertEqual((out / "runtime" / build_usb.STDLIB_ZIP).read_bytes(), first)   # powtarzalna budowa


class ThirdPartyLicensesTest(unittest.TestCase):
    def test_licences_match_the_pinned_runtimes(self):
        here = LAPTOP / "build" / "licencje"
        pins = json.loads((here / "zrodla.json").read_text(encoding="utf-8"))
        runtimes = json.loads((LAPTOP / "build" / "runtimes.json").read_text(encoding="utf-8"))
        self.assertEqual(pins["python"], runtimes["python"])   # nowa wersja: licencje pobiera się od nowa
        for r in runtimes["runtimes"].values():
            if r["kind"] == "pbs":
                self.assertIn(f"/download/{pins['pbs_release']}/", r["url"])
        names = pins["pbs"]["files"] + [pins["zstd"]["file"], pins["cpython"]["file"]]
        self.assertEqual(sorted(p.name for p in here.glob("LICENSE.*")), sorted(names))
        cpython = (here / pins["cpython"]["file"]).read_bytes()
        self.assertEqual(hashlib.sha256(cpython).hexdigest(), pins["cpython"]["sha256"])


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class SimulatorPreparationTest(unittest.TestCase):
    """The whole preparation against the bench-b firmware image, as the person at the laptop does it."""

    def setUp(self):
        self.sim = subprocess.Popen(["node", str(LAPTOP / "dev" / "sim-station.mjs"), "0"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.sim.stdout.close)
        self.addCleanup(self.sim.wait, 10)
        self.addCleanup(self.sim.stdin.close)
        port = int(self.sim.stdout.readline().split()[1])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = memory_journal(self.tmp.name)
        self.addCleanup(self.journal.close)
        self.station = usbproto.Station(f"tcp:127.0.0.1:{port}").start()
        self.addCleanup(self.station.stop)
        self.prep = Prep(self.station, self.journal)

    def wait(self, test, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if test():
                return
            time.sleep(0.05)
        self.fail(f"timeout: {self.station.state}")

    def test_preparation_flow(self):
        self.wait(lambda: self.station.state["phase"] == "connected")
        hello = self.station.state["hello"]
        self.assertEqual((hello["configured"], hello["prep"], hello["contracts"]), (False, False, [2]))
        doc = station_doc(addresses=["Szkoła A", "Hala „B”"])
        with self.assertRaises(OperationError) as e:
            self.prep.write_config(doc)
        self.assertEqual(e.exception.code, "prep_required")
        self.sim.stdin.write("prep\n")
        self.sim.stdin.flush()
        self.wait(lambda: (self.station.state["status"] or {}).get("prep"))
        written = self.prep.write_config(doc)
        self.assertEqual(written["config_seq"], 1)
        self.assertLessEqual(written["worst_request"], 220)
        self.assertEqual(self.prep.read_config()["doc"], doc)
        got = self.prep.card()["card"]
        key = bytes.fromhex(got["key"])
        fp = hashlib.sha256(key).hexdigest()[:16]
        self.assertEqual(got["fingerprint"], " ".join(fp[i:i + 4] for i in range(0, 16, 4)))
        self.assertEqual(got["lxmf"], configdoc.destination(key, "lxmf.delivery").hex())
        self.assertEqual(got["address"], doc["addresses"])
        with self.assertRaises(OperationError) as e:
            self.prep.write_config(station_doc(radio={"profile": "lora-sf7"}))   # obraz bench-b ma P1 na S2-LP
        self.assertEqual((e.exception.code, e.exception.field), ("invalid", "radio"))
        ops = [(x["op"], x["ok"]) for x in reversed(self.journal.recent())]
        self.assertEqual(ops, [("configure", False), ("configure", True), ("config_get", True), ("card", True),
                               ("configure", False)])

    def test_destroy_with_the_button_on_the_station(self):
        self.wait(lambda: self.station.state["phase"] == "connected")
        self.sim.stdin.write("prep\n")
        self.sim.stdin.flush()
        self.wait(lambda: (self.station.state["status"] or {}).get("prep"))
        self.prep.write_config(station_doc())
        kit = session.Session(Path(self.tmp.name) / "usb", Path(self.tmp.name) / "stan", iterations=1000)
        self.addCleanup(kit.close)
        (Path(self.tmp.name) / "usb").mkdir()
        kit.create(0)
        prep = Prep(self.station, kit)
        panel = Panel(self.station, prep, kit, "tok", {})

        def press(button):
            self.wait(lambda: (prep.destroy_state or {}).get("state") == "confirm")
            self.sim.stdin.write(f"press {button}\n")
            self.sim.stdin.flush()

        prep.destroy_station()
        press("BACK")                                       # WSTECZ = NIE
        self.wait(lambda: prep.destroy_state["state"] == "refused")
        self.assertIn("Nie potwierdzono", prep.destroy_state["message"])
        self.assertEqual(web.destroy(panel, {"confirm": "ZNISZCZ"}), {"usb": True, "station": "asking"})
        self.assertEqual(kit.describe()["kit"], "destroyed")   # laptop nie czeka na przycisk
        press("OK")
        self.wait(lambda: prep.destroy_state["state"] == "ok")
        self.wait(lambda: (self.station.state["hello"] or {}).get("configured") is False, timeout=30)
        with self.assertRaises(ValueError):
            web.destroy(panel, {})


if __name__ == "__main__":
    unittest.main()
