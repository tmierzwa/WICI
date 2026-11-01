# SPDX-License-Identifier: MIT
"""State-machine checks for the laptop's two-station migration coordinator."""

from pathlib import Path
import hashlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software" / "laptop"))
from wici import migration, migration_crypto  # noqa: E402
from wici import __main__ as wici_main  # noqa: E402
from wici.usbproto import ProtocolError, Rejected  # noqa: E402

MID = bytes(range(16))
TARGET_KEY = bytes(range(32))
EPH = bytes(range(32, 64))
PACKAGE_HASH = hashlib.sha256(b"source snapshot").digest()
HEADER = migration_crypto.make_header(MID, bytes(16), EPH, PACKAGE_HASH, migration.SNAPSHOT_SIZE)
PACKAGE = HEADER + bytes(migration.PACKAGE_SIZE - len(HEADER))
IMPORTED = "aa" * 32
RETIRED = "bb" * 32
ABORTED = "cc" * 32


class Link:
    def __init__(self, role, phase="none", fingerprint=None):
        self.role, self.phase = role, phase
        self.fingerprint = fingerprint or hashlib.sha256(MID + TARGET_KEY).hexdigest()[:16]
        self.calls = []
        self.aborted = False

    def request(self, type_, **fields):
        self.calls.append((type_, fields))
        if type_ != "migrate":
            raise AssertionError(type_)
        step = fields["step"]
        if step == "status":
            return {"type": "ok", "migration": self.phase, "mid": MID.hex() if self.phase != "none" else "",
                    "eph": EPH.hex() if self.phase in ("export", "retired") else "",
                    "package": PACKAGE_HASH.hex() if self.phase in ("export", "retired") else "",
                    "confirm": IMPORTED if self.role == "target" and self.phase == "imported" else
                               RETIRED if self.role == "source" and self.phase == "retired" else ""}
        if step == "receive_key" and self.role == "target":
            if self.phase == "none":
                self.phase = "receiving"
            return {"type": "ok", "mid": MID.hex(), "key": TARGET_KEY.hex(), "fingerprint": self.fingerprint}
        if step == "retire" and self.role == "source":
            assert fields["confirm"] == IMPORTED and self.phase in ("export", "retired")
            self.phase = "retired"
            return {"type": "ok", "confirm": RETIRED}
        if step == "abort" and self.role == "target":
            assert fields["mid"] == MID.hex()
            if self.phase == "none" and not self.aborted:
                raise Rejected({"type": "rejected", "reason": "migration"})
            self.phase, self.aborted = "none", True
            return {"type": "ok", **({"confirm": ABORTED} if fields["eph"] == EPH.hex() else {})}
        if step == "abort" and self.role == "source":
            assert (fields["mid"], fields["confirm"], self.phase) == (MID.hex(), ABORTED, "export")
            self.phase = "none"
            return {"type": "ok"}
        if step == "activate" and self.role == "target":
            assert fields["confirm"] == RETIRED
            self.phase = "none"
            return {"type": "ok"}
        raise AssertionError((self.role, step))

    def read_transfer(self, op, **fields):
        assert (self.role, op, fields) == ("source", "export", {"mid": MID.hex(), "target_key": TARGET_KEY.hex()})
        self.phase = "export"
        return PACKAGE

    def write_transfer(self, op, data, **fields):
        assert (self.role, op, fields) == ("target", "import", {"mid": MID.hex()})
        assert data == PACKAGE
        self.phase = "imported"
        return {"type": "ok", "confirm": IMPORTED}


class MigrationCoordinatorTest(unittest.TestCase):
    def test_packaged_cli_routes_to_migration(self):
        with mock.patch.object(migration, "main", return_value=0) as run:
            self.assertEqual(wici_main.main(["--migrate-source-port", "src", "--migrate-target-port", "dst"]), 0)
            self.assertEqual(wici_main.main(["--migrate-source-port", "src", "--migrate-target-port", "dst",
                                             "--migrate-abort"]), 0)
        self.assertEqual(run.call_args_list, [mock.call(["--source-port", "src", "--target-port", "dst"]),
                                              mock.call(["--source-port", "src", "--target-port", "dst", "--abort"])])

    def test_full_migration(self):
        source, target = Link("source"), Link("target")
        result = migration.migrate(source, target)
        self.assertEqual((result["mid"], result["activated"], source.phase, target.phase),
                         (MID.hex(), True, "retired", "none"))
        self.assertEqual(result["package_sha256"], hashlib.sha256(PACKAGE).hexdigest())

    def test_resumes_after_import_or_retirement(self):
        for source_phase in ("export", "retired"):
            source, target = Link("source", source_phase), Link("target", "imported")
            result = migration.migrate(source, target)
            self.assertTrue(result["activated"])
            self.assertEqual(source.phase, "retired")
            self.assertEqual(result["package_sha256"], None)

    def test_retired_source_is_asked_again_to_finish_its_erase(self):
        source, target = Link("source", "retired"), Link("target", "imported")
        migration.migrate(source, target)
        self.assertIn(("migrate", {"timeout": 60, "step": "retire", "mid": MID.hex(), "confirm": IMPORTED}),
                      source.calls)

    def test_abort_releases_the_source_only_with_the_target_confirmation(self):
        for target_phase in ("receiving", "importing", "imported", "none"):
            source, target = Link("source", "export"), Link("target", target_phase)
            target.aborted = target_phase == "none"   # repeated abort after a lost reply
            self.assertEqual(migration.abort(source, target), {"mid": MID.hex(), "aborted": True})
            self.assertEqual((source.phase, target.phase), ("none", "none"))
        source, target = Link("source"), Link("target", "receiving")
        migration.abort(source, target)
        self.assertEqual((target.phase, [c[1]["step"] for c in source.calls]), ("none", ["status"]))
        source, target = Link("source", "export"), Link("target")
        with self.assertRaises(Rejected):          # target without a record cannot release the source
            migration.abort(source, target)
        self.assertEqual(source.phase, "export")
        with self.assertRaisesRegex(ProtocolError, "retired"):
            migration.abort(Link("source", "retired"), Link("target", "imported"))
        with self.assertRaisesRegex(ProtocolError, "no migration"):
            migration.abort(Link("source"), Link("target"))

    def test_rejects_fingerprint_or_inconsistent_states(self):
        with self.assertRaisesRegex(ProtocolError, "fingerprint"):
            migration.migrate(Link("source"), Link("target", fingerprint="00" * 8))
        with self.assertRaisesRegex(ProtocolError, "target is empty"):
            migration.migrate(Link("source", "retired"), Link("target"))
        with self.assertRaisesRegex(ProtocolError, "no matching export"):
            migration.migrate(Link("source"), Link("target", "imported"))


if __name__ == "__main__":
    unittest.main()
