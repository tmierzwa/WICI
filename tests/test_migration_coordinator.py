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
from wici.usbproto import ProtocolError  # noqa: E402

MID = bytes(range(16))
TARGET_KEY = bytes(range(32))
EPH = bytes(range(32, 64))
PACKAGE_HASH = hashlib.sha256(b"source snapshot").digest()
HEADER = migration_crypto.make_header(MID, bytes(16), EPH, PACKAGE_HASH, migration.SNAPSHOT_SIZE)
PACKAGE = HEADER + bytes(migration.PACKAGE_SIZE - len(HEADER))
IMPORTED = "aa" * 32
RETIRED = "bb" * 32


class Link:
    def __init__(self, role, phase="none", fingerprint=None):
        self.role, self.phase = role, phase
        self.fingerprint = fingerprint or hashlib.sha256(MID + TARGET_KEY).hexdigest()[:16]
        self.calls = []

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
            assert fields["confirm"] == IMPORTED
            self.phase = "retired"
            return {"type": "ok", "confirm": RETIRED}
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
        with mock.patch.object(migration, "main") as run:
            self.assertEqual(wici_main.main(["--migrate-source-port", "src", "--migrate-target-port", "dst"]), 0)
        run.assert_called_once_with(["--source-port", "src", "--target-port", "dst"])

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

    def test_rejects_fingerprint_or_inconsistent_states(self):
        with self.assertRaisesRegex(ProtocolError, "fingerprint"):
            migration.migrate(Link("source"), Link("target", fingerprint="00" * 8))
        with self.assertRaisesRegex(ProtocolError, "target is empty"):
            migration.migrate(Link("source", "retired"), Link("target"))
        with self.assertRaisesRegex(ProtocolError, "no matching export"):
            migration.migrate(Link("source"), Link("target", "imported"))


if __name__ == "__main__":
    unittest.main()
