# SPDX-License-Identifier: MIT
"""Real TCP + real pyserial PTYs: RF is simulated and can be dropped independently."""
import json
import os
import pty
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import range_online as online
from test_range import reports
from range_test import R0_VERSION, summarize


class Online(unittest.TestCase):
    def test_private_addresses_only(self):
        for address in ('127.0.0.1', '100.101.102.103'):
            self.assertEqual(online.private_address(address), address)
        for address in ('0.0.0.0', '8.8.8.8', '192.168.1.1', '100.1.1.1'):
            with self.assertRaises(ValueError):
                online.private_address(address)

    def test_online_needs_both_completed_and_all_transmissions(self):
        a, b = reports()
        a['mode'] = b['mode'] = 'online'
        self.assertFalse(summarize(a, b)['valid_trial'])
        b['completed'] = True
        self.assertTrue(summarize(a, b)['passed'])
        b['events'] = b['events'][2:]
        self.assertFalse(summarize(a, b)['valid_trial'])

    def test_mixed_modes_rejected(self):
        a, b = reports()
        a['mode'] = 'online'
        with self.assertRaises(ValueError):
            summarize(a, b)

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_online_rf_loss_does_not_block_independent_b_transmission(self):
        self.exercise(drop=True)

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_online_two_processes(self):
        self.exercise(drop=False)

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_wrong_key_no_radio_transmission(self):
        self.exercise(wrong_key=True)

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_network_disconnect_keeps_local_report(self):
        self.exercise(disconnect=True)

    @unittest.skipUnless(os.name == 'posix', 'PTY required')
    def test_peer_usb_error_is_not_labelled_radio_loss(self):
        self.exercise(usb_error=True)

    def exercise(self, drop=False, wrong_key=False, disconnect=False, usb_error=False):
        pairs = [pty.openpty(), pty.openpty()]
        masters = [p[0] for p in pairs]
        buffers = {fd: b'' for fd in masters}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            tcp_port = sock.getsockname()[1]
        procs = []
        transmitted = []
        killed = False
        with tempfile.TemporaryDirectory() as folder:
            try:
                key = Path(folder)/'key'
                key.write_text('a'*64)
                badkey = Path(folder)/'badkey'
                badkey.write_text('b'*64)
                for i, role in enumerate('AB'):
                    procs.append(subprocess.Popen([sys.executable, str(ROOT/'tools/range_online.py'),
                        '--role', role, '--address', '127.0.0.1', '--tcp-port', str(tcp_port),
                        '--key-file', str(badkey if wrong_key and i == 1 else key),
                        '--port', os.ttyname(pairs[i][1]), '--point', 'P1', '--notes', 'stol',
                        '--count', '1', '--output', str(Path(folder)/role)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                    if i == 0:
                        time.sleep(.6)
                deadline = time.monotonic() + 25
                while any(p.poll() is None for p in procs) and time.monotonic() < deadline:
                    for fd in select.select(masters, [], [], .1)[0]:
                        buffers[fd] += os.read(fd, 4096)
                        while b'\n' in buffers[fd]:
                            line, buffers[fd] = buffers[fd].split(b'\n', 1)
                            i = masters.index(fd)
                            if line == b'INFO':
                                os.write(fd, f'INFO {R0_VERSION} DEVICE{i} 1 1 BOOT{i} 869.525 125 7 5 0 1.8\n'.encode())
                            elif line.startswith(b'TX '):
                                transmitted.append(i)
                                if usb_error:
                                    os.write(fd, b'ERR transmit -1\n')
                                    continue
                                os.write(fd, b'TX 0 '+line[3:]+b'\n')
                                if not (drop and i == 0):
                                    os.write(masters[1-i], b'RX -80 4 '+line[3:]+b'\n')
                                if disconnect and not killed:
                                    procs[1].kill()
                                    killed = True
                outputs = []
                for p in procs:
                    if p.poll() is None:
                        p.kill()
                    outputs.append(p.communicate(timeout=3))
                if usb_error:
                    self.assertTrue(all(p.returncode == 1 for p in procs), outputs)
                    categories = []
                    for role in 'AB':
                        p = next(p for p in (Path(folder)/role).glob('*.json') if not p.stem.endswith(('-peer', '-summary')))
                        categories.extend(e['category'] for e in json.loads(p.read_text())['issues'])
                    self.assertIn('usb', categories)
                    self.assertIn('peer-usb', categories)
                    return
                if disconnect:
                    a = json.loads(next(p for p in (Path(folder)/'A').glob('*.json') if not p.stem.endswith(('-peer', '-summary'))).read_text())
                    self.assertFalse(a['completed'])
                    self.assertTrue(any(e['category'] == 'internet' for e in a['issues']), (a, outputs))
                    return
                if wrong_key:
                    self.assertEqual(transmitted, [])
                    self.assertTrue(all(p.returncode == 1 for p in procs), outputs)
                    return
                self.assertTrue(all(p.returncode == 0 for p in procs), outputs)
                for role in 'AB':
                    summary = json.loads(next((Path(folder)/role).glob('*-summary.json')).read_text())
                    self.assertTrue(summary['valid_trial'])
                    self.assertEqual(summary['directions']['A->B']['received'], 0 if drop else 1)
                    self.assertEqual(summary['directions']['B->A']['sent'], 1)
                    self.assertEqual(summary['directions']['B->A']['received'], 1)
                    self.assertFalse(summary['passed'])  # abbreviated run
            finally:
                for p in procs:
                    if p.poll() is None:
                        p.kill();p.communicate()
                for m, s in pairs:
                    os.close(m);os.close(s)
