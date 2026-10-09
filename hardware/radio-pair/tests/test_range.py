# SPDX-License-Identifier: MIT
"""Offline two-host reports and two real pyserial processes over PTYs."""
import copy
import json
import os
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import range_test as rt


def reports(count=100):
    pair = []
    for role in 'AB':
        pair.append({'role': role, 'point': 'P1', 'notes': role, 'count': count,
                     'session': '0123456789abcdef', 'completed': role == 'A', 'issues': [],
                     'node': {'version': 'pair-0.2', 'ready': True, 'profile': rt.PROFILE, 'id': role},
                     'events': []})
    for seq in range(1, count + 1):
        for i, role in enumerate('AB'):
            text = rt.payload(pair[0]['session'], role, seq)
            pair[i]['events'].append({'kind': 'tx', 'status': 0, 'payload': text})
            pair[1-i]['events'].append({'kind': 'rx', 'rssi': -80, 'snr': 4, 'payload': text})
    return pair


class Reports(unittest.TestCase):
    def test_full_and_short(self):
        self.assertTrue(rt.summarize(*reports())['passed'])
        self.assertFalse(rt.summarize(*reports(1))['passed'])

    def test_lost_request_is_not_100_replies(self):
        a, b = reports()
        b['events'] = b['events'][2:]
        a['events'] = [e for e in a['events'] if e.get('payload') != rt.payload(a['session'], 'B', 1)]
        result = rt.summarize(a, b)
        self.assertTrue(result['valid_trial'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['directions']['A->B']['received'], 99)
        self.assertEqual(result['directions']['B->A']['sent'], 99)

    def test_duplicate_failed_tx_and_restart(self):
        a, b = reports()
        b['events'].append(copy.deepcopy(b['events'][0]))
        self.assertFalse(rt.summarize(a, b)['passed'])
        a, b = reports()
        a['events'][0]['status'] = -1
        self.assertFalse(rt.summarize(a, b)['valid_trial'])
        a, b = reports()
        b['issues'] = ['Restart']
        self.assertFalse(rt.summarize(a, b)['valid_trial'])

    def test_mismatch(self):
        for field, value in [('point', 'P2'), ('session', '1111111111111111'), ('count', 10)]:
            a, b = reports()
            b[field] = value
            with self.assertRaises(ValueError):
                rt.summarize(a, b)

    def test_no_radio_contact(self):
        a, b = reports()
        b['session'], b['events'] = None, []
        a['events'] = [e for e in a['events'] if e['kind'] == 'tx']
        result = rt.summarize(a, b)
        self.assertTrue(result['valid_trial'])
        self.assertFalse(result['passed'])
        self.assertIsNone(result['directions']['B->A']['delivery_percent'])

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_two_offline_host_processes(self):
        pairs = [pty.openpty(), pty.openpty()]
        masters = [p[0] for p in pairs]
        buffers = {fd: b'' for fd in masters}
        procs = []
        with tempfile.TemporaryDirectory() as folder:
            try:
                for index in (1, 0):  # listener first
                    out = Path(folder) / 'AB'[index]
                    procs.append(subprocess.Popen([sys.executable, str(ROOT/'tools/range_test.py'),
                        'run', '--role', 'AB'[index], '--port', os.ttyname(pairs[index][1]),
                        '--point', 'P1', '--notes', 'stol', '--count', '1', '--output', str(out)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                    if index == 1:
                        time.sleep(.5)
                deadline = time.monotonic() + 20
                while procs[1].poll() is None and time.monotonic() < deadline:
                    for fd in select.select(masters, [], [], .1)[0]:
                        buffers[fd] += os.read(fd, 4096)
                        while b'\n' in buffers[fd]:
                            line, buffers[fd] = buffers[fd].split(b'\n', 1)
                            i = masters.index(fd)
                            if line == b'INFO':
                                os.write(fd, f'INFO pair-0.2 DEVICE{i} 1 1 BOOT{i} 869.525 125 7 5 0 1.8\n'.encode())
                            elif line.startswith(b'TX '):
                                os.write(fd, b'TX 0 ' + line[3:] + b'\n')
                                os.write(masters[1-i], b'RX -80 4 ' + line[3:] + b'\n')
                self.assertEqual(procs[1].poll(), 0)
                procs[0].send_signal(signal.SIGINT)
                for proc in procs:
                    stdout, stderr = proc.communicate(timeout=3)
                    self.assertEqual(proc.returncode, 0, (stdout, stderr))
                a, b = [json.loads(next((Path(folder)/role).glob('*.json')).read_text()) for role in 'AB']
                result = rt.summarize(a, b)
                self.assertTrue(result['valid_trial'])
                self.assertEqual(result['directions']['A->B']['received'], 1)
                self.assertEqual(result['directions']['B->A']['received'], 1)
                self.assertFalse(result['passed'])
            finally:
                for proc in procs:
                    if proc.poll() is None:
                        proc.kill(); proc.communicate()
                for m, s in pairs:
                    os.close(m); os.close(s)
