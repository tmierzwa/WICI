import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pair_test import decode, judge

class PairResults(unittest.TestCase):
    def events(self, payload='expected'):
        return [('A', decode('TX 0 ' + payload)), ('B', decode('RX -60.5 9.0 ' + payload))]
    def test_success(self):
        self.assertTrue(judge(self.events(), 'A', 'expected')['ok'])
    def test_missing_and_wrong_payload(self):
        for events in (self.events()[:1], self.events('old-session'), self.events()[1:]):
            self.assertFalse(judge(events, 'A', 'expected')['ok'])
    def test_duplicate_not_success(self):
        events = self.events()
        self.assertFalse(judge(events + [events[1]], 'A', 'expected')['ok'])
    def test_failed_tx_not_success(self):
        events = [('A', decode('TX -2 expected')), self.events()[1]]
        self.assertFalse(judge(events, 'A', 'expected')['ok'])
    def test_wrong_direction(self):
        self.assertFalse(judge(self.events(), 'B', 'expected')['ok'])
    def test_error(self):
        self.assertFalse(judge(self.events()+[('B', decode('ERR read -7'))], 'A', 'expected')['ok'])
    def test_info(self):
        item = decode('INFO pair-0.1 ABCDEF 1 1 12345678 869.525 125 7 5 0 1.8')
        self.assertEqual(item['kind'], 'info')
        self.assertTrue(item['ready'])
        self.assertEqual(item['boot'], '12345678')
    def test_noise(self):
        for line in ('', 'RX bad', 'TX xx p', 'booting', 'RX -50 8 payload injected'):
            self.assertEqual(decode(line)['kind'], 'other')

if __name__ == '__main__':
    unittest.main()
