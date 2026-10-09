"""Delivery must match the exact sources and binary that were verified."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import package
import radio_test


class PackageChecks(unittest.TestCase):
    def fixture(self, root):
        (root / 'src').mkdir()
        source = root / 'src/main.cpp'
        source.write_text('verified source')
        firmware = root / 'firmware.bin'
        firmware.write_bytes(b'verified image')
        evidence = {'compiled': True, 'automated_tests': 1, 'automated_tests_passed': 1,
                    'source_sha256': {'src/main.cpp': package.checksum(source)},
                    'firmware_bin_sha256': package.checksum(firmware)}
        (root / 'checks.json').write_text(json.dumps(evidence))
        return source, firmware

    def test_stale_source_or_added_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, firmware = self.fixture(root)
            package.verify_source(root, firmware)
            source.write_text('unverified source')
            with self.assertRaises(RuntimeError):
                package.verify_source(root, firmware)
            source.write_text('verified source')
            (root / 'src/new.cpp').write_text('new unverified file')
            with self.assertRaises(RuntimeError):
                package.verify_source(root, firmware)

    def test_different_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, firmware = self.fixture(root)
            firmware.write_bytes(b'different image')
            with self.assertRaises(RuntimeError):
                package.verify_source(root, firmware)

    def test_host_and_firmware_protocol_constants_match(self):
        import re
        import diagnose
        root = Path(__file__).resolve().parents[1]
        header = (root / 'src/diagnostic.h').read_text()
        self.assertEqual(re.search(r'VERSION = "([^"]+)"', header)[1], radio_test.L0_VERSION)
        for name in ('MIX_DURATION_MS', 'MIX_MAX_GAP_MS'):
            self.assertEqual(int(re.search(name + r' = (\d+)', header)[1]), getattr(diagnose, name))
        self.assertEqual(diagnose.FRAM_SIZE, 512 * 1024)
