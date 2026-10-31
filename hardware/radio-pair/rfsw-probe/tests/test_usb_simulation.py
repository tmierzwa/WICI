"""Pseudo-terminals exercise the real pyserial runner (pattern of radio-pair), not physical RF."""
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = [b'RX H -40.0 12.0 RFSW1', b'RX RH -41.0 11.5 RFSW2', b'RX L -71.0 1.5 RFSW3',
          b'MISS RL', b'RX H -41.0 11.5 RFSW5', b'RX RH -42.0 11.0 RFSW6', b'MISS L',
          b'RX RL -70.0 2.0 RFSW8']


@unittest.skipUnless(os.name == 'posix', 'Requires POSIX pseudo-terminals')
class UsbSimulation(unittest.TestCase):
    def test_beacon_and_receive_report(self):
        code, stdout, report = self.exercise(rx_reset=21)  # USB-Serial-JTAG chip reset
        self.assertEqual(code, 0, stdout)
        self.assertTrue(report['completed'])
        self.assertEqual({k: (v['received'], v['missed']) for k, v in report['summary'].items()},
                         {'H': (2, 0), 'RH': (2, 0), 'L': (1, 1), 'RL': (1, 1)})
        self.assertEqual(report['grid_mismatches'], 0)
        self.assertIn('podciąganiem w górę 1', stdout)

    def test_reset_other_than_power_on_is_refused(self):
        code, stdout, report = self.exercise(rx_reset=3)  # ROM SW_SYS_RESET: registers may be stale
        self.assertNotEqual(code, 0)
        self.assertFalse(report['completed'])
        self.assertIn('odłącz i podłącz USB', report['error'])
        self.assertEqual(sum(v['received'] for v in report['summary'].values()), 0)

    def exercise(self, rx_reset):
        import serial  # dependency check; PTYs use real pyserial
        del serial
        pairs = [pty.openpty(), pty.openpty()]  # 0: tx kit, 1: rx kit
        masters = [p[0] for p in pairs]
        buffers = {fd: b'' for fd in masters}
        resets = [1, rx_reset]
        with tempfile.TemporaryDirectory() as output:
            proc = subprocess.Popen([sys.executable, str(ROOT / 'tools/rfsw_test.py'),
                                     '--tx', os.ttyname(pairs[0][1]), '--rx', os.ttyname(pairs[1][1]),
                                     '--count', '2', '--output', output],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 20
                while proc.poll() is None and time.monotonic() < deadline:
                    readable, _, _ = select.select(masters, [], [], .1)
                    for fd in readable:
                        buffers[fd] += os.read(fd, 4096)
                        while b'\n' in buffers[fd]:
                            line, buffers[fd] = buffers[fd].split(b'\n', 1)
                            index = masters.index(fd)
                            if line == b'INFO':
                                # Twice: the boot INFO after the port reset, then the reply.
                                os.write(fd, 2 * (f'INFO rfsw-0.3 DEVICE{index} 1 {resets[index]} mux=00000A00 '
                                                  f'mcu_sel=1 ie=1 pu=0 pd=0 drv=2 oe=0 out_sel=00000100 '
                                                  f'up=1 down=0 fh=1 fl=0\n').encode())
                            elif line == b'BEACON':
                                os.write(fd, b'BEACON\nTX 0 RFSW1\n')
                            elif line == b'RECEIVE':
                                # Split writes: a record cut by the read timeout must stay whole.
                                data = b'RECEIVE\n' + b'\n'.join(SCRIPT) + b'\n'
                                os.write(fd, data[:30]); time.sleep(.25); os.write(fd, data[30:])
                if proc.poll() is None:
                    proc.kill()
                stdout, stderr = proc.communicate(timeout=3)
                reports = list(Path(output).glob('rfsw-*-DEVICE1.json'))
                self.assertEqual(len(reports), 1, (stdout, stderr))
                return proc.returncode, stdout.decode() + stderr.decode(), json.loads(reports[0].read_text())
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait()
                for master, slave in pairs:
                    os.close(master); os.close(slave)


if __name__ == '__main__':
    unittest.main()
