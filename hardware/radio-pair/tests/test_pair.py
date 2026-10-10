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
        self.assertFalse(judge(self.events()+[('B', decode('ERR receive -2'))], 'A', 'expected')['ok'])
    def test_crc_failure_is_radio_loss(self):
        self.assertEqual(decode('ERR read -7')['kind'], 'corrupt')
        self.assertEqual(decode('ERR read -2')['kind'], 'error')
        result = judge(self.events()[:1] + [('B', decode('ERR read -7'))], 'A', 'expected')
        self.assertFalse(result['ok'])
        self.assertEqual((result['corrupt_records'], result['errors']), (1, []))
    def test_info(self):
        item = decode('INFO pair-0.3 ABCDEF 1 1 12345678 869.525 125 7 5 0 1.8')
        self.assertEqual(item['kind'], 'info')
        self.assertTrue(item['ready'])
        self.assertEqual(item['boot'], '12345678')
    def test_noise(self):
        for line in ('', 'booting'):
            self.assertEqual(decode(line)['kind'], 'other')

    def test_malformed_record_is_error(self):
        for line in ('RX bad', 'TX xx p', 'RX -50 8 payload injected', 'RX nan 9 p'):
            self.assertEqual(decode(line)['kind'], 'error')

    def test_silence_aborts_radio_trial(self):
        self.assertFalse(judge(self.events()+[('A', decode('BLOCKED SILENCE'))], 'A', 'expected')['ok'])

if __name__ == '__main__':
    unittest.main()
