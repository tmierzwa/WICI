# SPDX-License-Identifier: MIT
"""Audit regressions that do not require local network ports."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'software/laptop'))
from wici import database, session, web


class CopyAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.usb = self.root / 'usb'
        self.usb.mkdir()
        self.kit, self.key = database.Kit.create(self.usb / 'keys', {'gospodarz': 'test'}, 'recovery', iterations=1000)
        self.db = database.Database(self.key, self.root / 'disk', self.usb / 'kopia',
                                    schema='CREATE TABLE events(value TEXT);', kit_id=database.kit_id(self.usb / 'keys'))
        self.db.write(lambda c: c.execute("INSERT INTO events VALUES ('first')"))
        self.db.flush()

    def tearDown(self):
        if (self.root / 'away').exists():
            (self.root / 'away').rename(self.usb)
        self.db.close()
        self.tmp.cleanup()

    def test_removal_and_return_without_another_write(self):
        self.assertTrue(self.db.status()['usb_saved'])
        self.usb.rename(self.root / 'away')
        status = self.db.status()
        self.assertFalse(status['usb_present'])
        self.assertFalse(status['usb_saved'])
        self.assertEqual(status['usb_problem'], database.NO_USB)
        with self.assertRaises(database.StorageError):
            self.db.flush()
        (self.root / 'away').rename(self.usb)
        self.assertTrue(self.db.status()['usb_saved'])

    def test_foreign_stick_cannot_be_reported_as_current(self):
        keyfile = self.usb / 'keys/zestaw.key'
        key = keyfile.read_bytes()
        try:
            keyfile.write_bytes(os.urandom(32))
            status = self.db.status()
            self.assertEqual(status['usb_problem'], database.WRONG_USB)
            self.assertFalse(status['usb_saved'])
        finally:
            keyfile.write_bytes(key)

    def test_unpersisted_change_is_not_covered_by_old_usb_copy(self):
        with self.db.cond:
            self.db.changes += 1
        self.assertFalse(self.db.status()['usb_saved'])
        with self.db.cond:
            self.db.changes -= 1

    def test_write_error_is_not_a_successful_copy(self):
        self.db.usb_error = 'no space'
        self.assertFalse(self.db.status()['usb_saved'])
        self.db.usb_error = None

    def test_empty_password_has_operator_message(self):
        with self.assertRaisesRegex(ValueError, 'Wpisz hasło z koperty'):
            web._text({'password': ''}, 'password')


class RecoveryTest(unittest.TestCase):
    def test_recovery_preserves_journal_and_new_login_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); usb = root / 'usb'; usb.mkdir()
            first = session.Session(usb, root / 'state1', iterations=1000)
            envelopes = first.create(2)['envelopes']
            recovery = next(x['password'] for x in envelopes if x['account'] == 'odtworzenie')
            first.add('test', '', 'test_before_recovery', True)
            first.close()
            (usb / 'keys/konta.json').unlink()
            restored = session.Session(usb, root / 'state2', iterations=1000)
            envelopes = restored.recover(recovery, 2)['envelopes']
            password = next(x['password'] for x in envelopes if x['account'] == 'gospodarz')
            self.assertIn('test_before_recovery', [x['op'] for x in restored.recent()])
            restored.logout()
            restored.login('gospodarz', password)
            self.assertEqual(restored.user, 'gospodarz')
            self.assertIn('kit_recover', [x['op'] for x in restored.recent()])
            restored.close()
