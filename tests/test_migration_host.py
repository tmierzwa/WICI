# SPDX-License-Identifier: MIT
"""PRZENIEŚ STACJĘ end to end on the real station program (firmware/src/main.cpp, BenchHost::migration*).

Two bench-b station programs from the simulator's native build (software/simulator/build.py --native) talk the
USB data protocol "usb":2 with the laptop's own coordinator (software/laptop/wici/migration.py, usbproto.Link).
Each program is a process; FRAM, NVS and RTC memory live in files between processes, so a power loss is a
process that ends after its FRAM was saved, and `cut <bytes>` (hal/vboard.cpp) cuts the FRAM supply in the
middle of a command.

  python3 software/simulator/build.py --native   # or WICI_SIM_PROGRAM=<program>
  python3 -m unittest tests.test_migration_host
"""

import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
sys.path.insert(0, str(ROOT / "software" / "reference"))
from reference import crc16  # noqa: E402
from wici import migration, usbproto  # noqa: E402

PROGRAM = Path(os.environ.get("WICI_SIM_PROGRAM", ROOT / "software" / "simulator" / "build" / "wici-station"))
POWER_ON, SOFTWARE = 1, 3
STEP_US = 10_000          # virtual time per read of the USB data port
PRESS_US = 150_000


class Board:
    """One station program; its non-volatile memory in files of `directory`."""

    def __init__(self, directory, seed):
        self.dir, self.seed = Path(directory), seed
        self.dir.mkdir(parents=True, exist_ok=True)
        self.process, self.now, self.ports = None, 0, set()   # open USB interfaces: 0 diagnostics, 1 data
        self.lock = threading.RLock()
        self.air = []          # frames this station transmitted, with the process generation
        self.generation = 0

    def cmd(self, line):
        with self.lock:   # the USB reader thread and the test share the process
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()
            out = []
            for reply in self.process.stdout:
                if reply == ".\n":
                    return "\n".join(out)
                out.append(reply.rstrip("\n"))
        raise RuntimeError(f"station program ended: {line}")

    def power_on(self, reason=POWER_ON):
        with self.lock:
            self.process = subprocess.Popen([str(PROGRAM)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            self.generation += 1
            self.cmd(f"boot {self.now} {reason} {self.seed}")
            for name in ("fram", "noinit") if reason == SOFTWARE else ("fram",):
                if (self.dir / name).exists():
                    assert self.cmd(f"{name} load {self.dir / name}") == "ok"
            if (self.dir / "nvs").exists():
                self.cmd("nvs " + (self.dir / "nvs").read_text())
            self.pins = json.loads(self.cmd("pins"))
            for itf in self.ports:
                self.cmd(f"usb {itf} open")

    def power_off(self, software=False):
        """Keep FRAM and NVS (and RTC memory for a software restart), then end the process."""
        with self.lock:
            self.take_air()
            assert self.cmd(f"fram save {self.dir / 'fram'}") == "ok"
            if software:
                assert self.cmd(f"noinit save {self.dir / 'noinit'}") == "ok"
            (self.dir / "nvs").write_text(self.cmd("nvs"))
            self.process.stdin.close()
            self.process.wait(10)
            self.process.stdout.close()
            self.process = None

    def take_air(self):
        self.air += [(self.generation, f) for f in json.loads(self.cmd("air"))]

    def advance(self, us):
        self.run_to(self.now + us)

    def run_to(self, t):
        """Run until world time t; a software restart continues in a new process from the restart time."""
        with self.lock:
            t = max(self.now, t)
            while self.cmd(f"run {t}").startswith("reboot"):
                self.now = json.loads(self.cmd("state"))["world_us"]
                self.power_off(software=True)
                self.power_on(SOFTWARE)
            self.now = t

    def fram(self):
        with self.lock:
            assert self.cmd(f"fram save {self.dir / 'fram'}") == "ok"
        return (self.dir / "fram").read_bytes()

    def pin(self, name, level):
        self.cmd(f"pin {self.pins[name]} {level}")

    def press(self, name, us=PRESS_US):
        with self.lock:
            self.pin(name, 0)
            self.advance(us)
            self.pin(name, 1)
            self.advance(PRESS_US)

    def open_usb(self):
        with self.lock:
            self.ports.add(1)
            self.cmd("usb 1 open")
        return Port(self)

    def write_usb(self, data):
        text = data.hex()
        for i in range(0, len(text), 8000):
            self.cmd(f"usbin 1 {text[i:i + 8000]}")

    def read_usb(self):
        return bytes.fromhex(self.cmd("usbout 1"))


class Port:
    """The USB data port for usbproto.Link: each read runs the station; a duty officer presses OK on `pending`."""

    def __init__(self, board):
        self.board, self.text = board, b""

    def read(self, _timeout):
        with self.board.lock:
            if self.board.process is None:
                return b""
            self.board.advance(STEP_US)
            data = self.board.read_usb()
            *lines, self.text = (self.text + data).split(b"\n")
            if any(b'"type":"pending"' in line for line in lines):
                self.board.press("OK")
        if not data:
            time.sleep(0.001)
        return data

    def write(self, data):
        with self.board.lock:
            self.board.write_usb(data)

    def close(self):
        with self.board.lock:
            self.board.ports.discard(1)
            if self.board.process is not None:
                self.board.cmd("usb 1 close")


COUNTER_AREA = slice(0x044100, 0x044180)    # envelope counter records, two copies per receiver identity
SOURCE_BOUND = 4096                        # the source's reserved envelope counter bound before the migration


def receiver_card():
    """A legacy receiver card: random public keys and their LXMF addresses."""
    entry = lambda key: {"lxmf": usbproto.configdoc.destination(key, "lxmf.delivery").hex(), "key": key.hex()}
    return {"main": entry(os.urandom(64)), "backup": entry(os.urandom(64))}


def counter_record(sequence, upper):
    """A committed envelope counter record (firmware/src/envelope_counter.cpp), not yet bound to a key."""
    body = b"WCT1" + bytes(6) + sequence.to_bytes(4, "big") + upper.to_bytes(4, "big") + bytes(8)
    return body + crc16(body).to_bytes(2, "big") + bytes(3) + b"\xa5"


def upper_bound(fram, peer=0):
    """The newest committed upper bound in a receiver identity's counter slot."""
    records = [fram[COUNTER_AREA.start + (peer * 2 + i) * 32:][:32] for i in range(2)]
    committed = [r for r in records if r[:4] == b"WCT1" and r[31] == 0xA5]
    return int.from_bytes(max(committed, key=lambda r: int.from_bytes(r[10:14], "big"))[14:18], "big")


def set_prep(board, link, on):
    """Hold the preparation button when the mode differs; the mode afterwards."""
    if link.request("status")["prep"] != on:
        board.pin("PREP", 0)
        board.advance(3_200_000)
        board.pin("PREP", 1)
        board.advance(200_000)
    return link.request("status")["prep"]


def prep_session(board):
    """A USB session in preparation mode."""
    link = usbproto.Link(board.open_usb())
    if not link.wait_hello(5) or not set_prep(board, link, True):
        raise AssertionError("no session in preparation mode")
    return link


@unittest.skipUnless(PROGRAM.is_file(), "simulator program not built (software/simulator/build.py --native)")
class MigrationHostTest(unittest.TestCase):
    """Each test starts from one prepared pair: a configured source and an empty target, both in preparation."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        source, target = Board(Path(cls.base.name) / "source", 2), Board(Path(cls.base.name) / "target", 3)
        for board in (source, target):
            board.power_on()
            board.advance(20_000_000)   # silence debt of the cold start
        with contextlib.closing(prep_session(source)) as link:
            link.write_transfer("configure", usbproto.configdoc.compact({
                "role": "stacja", "addresses": ["Szkoła, ul. Polna 12"], "receiver": receiver_card(), "stations": 2,
                "phrases": [], "ifac": "ab" * 16, "radio": {"profile": "p1"}}, usbproto.configdoc.DOC_MAX))
            cls.lxmf = link.request("card")["lxmf"]
        prep_session(target).close()
        # bench-b has no WICI-Link radio, so the reservation a numbered source would have made is
        # written as its counter record; the migration must carry it like any other byte of the image.
        source.power_off()
        fram = bytearray((source.dir / "fram").read_bytes())
        fram[COUNTER_AREA.start + 32:COUNTER_AREA.start + 64] = counter_record(1, SOURCE_BOUND)
        (source.dir / "fram").write_bytes(fram)
        target.power_off()
        cls.counters = bytes(fram[COUNTER_AREA])
        cls.clock = {"source": source.now, "target": target.now}

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shutil.copytree(self.base.name, tmp.name, dirs_exist_ok=True)
        self.source, self.target = Board(Path(tmp.name) / "source", 2), Board(Path(tmp.name) / "target", 3)
        self.links = {}
        self.addCleanup(self.shutdown)
        for name, board in (("source", self.source), ("target", self.target)):
            board.now = self.clock[name]
            board.power_on()
            self.connect(board)

    def shutdown(self):
        for board in (self.source, self.target):
            self.disconnect(board)
            if board.process is not None:
                board.power_off()

    def connect(self, board):
        self.disconnect(board)
        self.links[board] = prep_session(board)

    def hello(self, board):
        """The station's `hello` on a new USB session."""
        self.disconnect(board)
        board.advance(1_000_000)
        link = self.links[board] = usbproto.Link(board.open_usb())
        return link.wait_hello(5)

    def disconnect(self, board):
        link = self.links.pop(board, None)
        if link is not None:
            link.close()

    def power_cut(self, *boards):
        """Power loss between USB commands: the process ends, FRAM stays."""
        for board in boards:
            self.disconnect(board)
            board.power_off()
            board.power_on()
            self.connect(board)

    def phase(self, board):
        set_prep(board, self.links[board], True)   # an activated target has left preparation
        return self.links[board].request("migrate", step="status")["migration"]

    def migrate(self):
        return migration.migrate(self.links[self.source], self.links[self.target])

    def leave_prep(self, board):
        """Hold the preparation button in preparation; True when the station stays in it."""
        return set_prep(board, self.links[board], False)

    def transmits(self, board, minutes):
        board.take_air()
        before = len(board.air)
        for _ in range(minutes):
            board.advance(60_000_000)
        board.take_air()
        return len(board.air) > before

    def assert_migrated(self):
        """The target runs with the source identity and counters; the retired source never transmits."""
        self.assertEqual((self.phase(self.source), self.phase(self.target)), ("retired", "none"))
        self.assertEqual(self.hello(self.target)["lxmf"], self.lxmf)
        fram = self.target.fram()
        self.assertEqual(fram[COUNTER_AREA], self.counters)
        self.assertGreaterEqual(upper_bound(fram), SOURCE_BOUND)
        self.assertFalse(self.leave_prep(self.target))
        self.assertTrue(self.transmits(self.target, 5))
        self.assertTrue(self.leave_prep(self.source))   # a retired source stays in preparation ...
        self.assertFalse(self.transmits(self.source, 30))   # ... and silent
        self.assertEqual(self.hello(self.source)["lxmf"], "")

    def test_full_migration(self):
        result = self.migrate()
        self.assert_migrated()
        retired = self.links[self.source].request("migrate", step="status")["confirm"]
        self.assertTrue(set_prep(self.target, self.links[self.target], True))
        again = self.links[self.target].request("migrate", step="activate", mid=result["mid"], confirm=retired)
        self.assertTrue(again.get("duplicate"))   # a lost reply is safe to repeat

    def steps(self, last):
        """The coordinator's steps up to `last` (receive_key, export, import, retire); their results."""
        source, target = self.links[self.source], self.links[self.target]
        key = target.request("migrate", step="receive_key")
        done = {"mid": key["mid"]}
        if last != "receive_key":
            done["package"] = source.read_transfer("export", mid=key["mid"], target_key=key["key"])
        if last in ("import", "retire"):
            done["imported"] = target.write_transfer("import", done["package"], mid=key["mid"])["confirm"]
        if last == "retire":
            done["retired"] = source.request("migrate", timeout=60, step="retire", mid=key["mid"],
                                             confirm=done["imported"])["confirm"]
        return done

    def resume_after_power_loss(self, last, phases):
        self.steps(last)
        self.power_cut(self.source, self.target)
        self.assertEqual((self.phase(self.source), self.phase(self.target)), phases)
        for board in (self.source, self.target):   # locked in preparation and silent
            self.assertTrue(self.leave_prep(board))
            self.assertFalse(self.transmits(board, 5))
        self.migrate()
        self.assert_migrated()

    def test_power_loss_after_export(self):
        self.resume_after_power_loss("export", ("export", "receiving"))

    def test_power_loss_after_import(self):
        self.resume_after_power_loss("import", ("export", "imported"))

    def test_power_loss_after_retire(self):
        self.resume_after_power_loss("retire", ("retired", "imported"))
        set_prep(self.target, self.links[self.target], True)
        with self.assertRaises(migration.ProtocolError):   # a retired source cannot be withdrawn
            migration.abort(self.links[self.source], self.links[self.target])

    def test_power_loss_during_activate(self):
        """FRAM loses power after n bytes of activate, for every n: the target is imported or activated, never lost."""
        done = self.steps("retire")
        self.disconnect(self.target)
        self.target.power_off()
        imported = Path(tempfile.mkdtemp(dir=self.target.dir.parent))
        shutil.copytree(self.target.dir, imported, dirs_exist_ok=True)
        start, activated = self.target.now, None
        for kept in range(0, 4096):
            shutil.copytree(imported, self.target.dir, dirs_exist_ok=True)
            self.target.now = start
            self.target.power_on()
            self.connect(self.target)
            self.target.cmd(f"cut {kept}")
            with contextlib.suppress(usbproto.ProtocolError, usbproto.Rejected):
                self.links[self.target].request("migrate", step="activate", mid=done["mid"], confirm=done["retired"])
            self.power_cut(self.target)
            phase = self.phase(self.target)
            self.assertIn(phase, ("imported", "none"), kept)
            if phase == "none":
                activated = kept if activated is None else activated
            else:
                self.assertIsNone(activated, f"{kept} B kept rolled back the activation of {activated} B")
            again = self.links[self.target].request("migrate", step="activate", mid=done["mid"], confirm=done["retired"])
            self.assertEqual(again.get("duplicate", False), phase == "none", kept)
            self.disconnect(self.target)
            self.target.power_off()
            if activated is not None and kept >= activated + 64:
                break
        self.assertIsNotNone(activated)
        self.target.power_on()
        self.connect(self.target)
        self.assert_migrated()

    def test_target_abort_before_export(self):
        key = self.steps("receive_key")
        self.assertEqual(migration.abort(self.links[self.source], self.links[self.target]),
                         {"mid": key["mid"], "aborted": True})
        self.target.advance(60_000_000)   # it restarts; a new receive_key waits for the cold start silence debt
        self.assertEqual(self.phase(self.target), "none")
        self.assertNotEqual(self.links[self.target].request("migrate", step="receive_key")["mid"], key["mid"])
        self.migrate()   # the transfer key of the withdrawn attempt is not needed again
        self.assert_migrated()

    def check_source_restored(self, last):
        done = self.steps(last)
        source = self.links[self.source]
        with self.assertRaises(usbproto.Rejected) as forged:
            source.request("migrate", step="abort", mid=done["mid"], confirm="00" * 32)
        self.assertEqual(forged.exception.reason, "signature")
        self.assertEqual(migration.abort(source, self.links[self.target]), {"mid": done["mid"], "aborted": True})
        for board in (self.source, self.target):
            board.advance(5_000_000)   # both restart after their abort
        self.assertEqual((self.phase(self.source), self.phase(self.target)), ("none", "none"))
        # A lost reply: the target repeats its "aborted" confirmation and the source accepts it again.
        eph_abort = self.links[self.target].request("migrate", step="abort", mid=done["mid"], eph="")
        self.assertTrue(eph_abort["duplicate"])
        self.phase(self.source)
        self.assertTrue(source.request("migrate", step="abort", mid=done["mid"], confirm=eph_abort["confirm"])
                        ["duplicate"])
        self.assertEqual(self.hello(self.source)["lxmf"], self.lxmf)
        self.assertFalse(self.leave_prep(self.source))
        self.assertTrue(self.transmits(self.source, 5))

    def test_abort_after_export_restores_source(self):
        self.check_source_restored("export")

    def test_abort_after_import_restores_source(self):
        self.check_source_restored("import")   # the target asks for OK before erasing an import

