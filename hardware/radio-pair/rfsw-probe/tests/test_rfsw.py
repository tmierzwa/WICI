import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rfsw_test  # noqa: E402

INFO = ('INFO rfsw-0.3 A028AD76B144 1 1 mux=00000A00 mcu_sel=1 ie=1 pu=0 pd=0 drv=2 oe=0 '
        'out_sel=00000100 up=1 down=0 fh=1 fl=0')


def decode_all(lines):
    return [rfsw_test.decode(x) for x in lines]


class DecodeTest(unittest.TestCase):
    def test_info(self):
        e = rfsw_test.decode(INFO)
        self.assertEqual(e['kind'], 'info')
        self.assertEqual((e['id'], e['ready'], e['reset']), ('A028AD76B144', True, 1))
        self.assertEqual((e['ie'], e['pu'], e['pd'], e['oe']), ('1', '0', '0', '0'))
        self.assertEqual((e['up'], e['down'], e['fh'], e['fl']), ('1', '0', '1', '0'))

    def test_records(self):
        self.assertEqual(rfsw_test.decode('RX RL -61.5 9.0 RFSW12'),
                         {'kind': 'rx', 'state': 'RL', 'rssi': -61.5, 'snr': 9.0, 'seq': 12})
        self.assertEqual(rfsw_test.decode('MISS RH'), {'kind': 'miss', 'state': 'RH'})
        self.assertEqual(rfsw_test.decode('BAD H -7'), {'kind': 'bad', 'state': 'H', 'code': -7})
        self.assertEqual(rfsw_test.decode('TX 0 RFSW3'), {'kind': 'tx', 'status': 0, 'payload': 'RFSW3'})
        self.assertEqual(rfsw_test.decode('ERR receive -2')['kind'], 'error')

    def test_malformed(self):
        self.assertEqual(rfsw_test.decode('RX H x 1 RFSW1')['kind'], 'error')
        self.assertEqual(rfsw_test.decode('RX Q -1 1 RFSW1')['kind'], 'error')
        self.assertEqual(rfsw_test.decode('BAD H')['kind'], 'error')
        self.assertEqual(rfsw_test.decode('INFO pair-0.4 X')['kind'], 'error')
        self.assertEqual(rfsw_test.decode('RECEIVE')['kind'], 'other')


class SummaryTest(unittest.TestCase):
    def test_per_state(self):
        events = decode_all(['RX H -40.0 12.0 RFSW1', 'RX RH -41.0 11.0 RFSW2', 'RX L -70.0 2.0 RFSW3',
                             'MISS RL', 'RX H -42.0 11.0 RFSW5', 'BAD RH -7', 'BAD L 0'])
        s = rfsw_test.summarize(events)
        self.assertEqual((s['H']['received'], s['H']['missed']), (2, 0))
        self.assertEqual(s['H']['rssi'], {'median': -41.0, 'min': -42.0, 'max': -40.0})
        self.assertEqual((s['RH']['received'], s['RH']['crc'], s['RH']['foreign']), (1, 1, 0))
        self.assertEqual((s['L']['received'], s['L']['foreign']), (1, 1))
        self.assertEqual((s['RL']['received'], s['RL']['missed']), (0, 1))
        self.assertIsNone(s['RL']['snr'])

    def test_grid(self):
        # One beacon lost (MISS between 3 and 5): consistent.
        ok = decode_all(['RX H -40 12 RFSW3', 'MISS RH', 'RX L -70 2 RFSW5', 'BAD RL -7', 'RX H -40 12 RFSW7'])
        self.assertEqual(rfsw_test.grid_mismatches(ok), 0)
        # A lost beacon hidden in a window (no MISS between 3 and 5): flagged.
        hidden = decode_all(['RX H -40 12 RFSW3', 'RX RH -41 11 RFSW5'])
        self.assertEqual(rfsw_test.grid_mismatches(hidden), 1)
        # A foreign packet takes a window without a beacon: flagged.
        foreign = decode_all(['RX H -40 12 RFSW3', 'BAD RH 0', 'RX L -70 2 RFSW4'])
        self.assertEqual(rfsw_test.grid_mismatches(foreign), 1)


if __name__ == '__main__':
    unittest.main()
