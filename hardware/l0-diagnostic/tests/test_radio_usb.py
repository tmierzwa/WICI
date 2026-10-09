"""macOS/Linux pseudo-terminals exercise the real pyserial runner, not physical RF."""
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

@unittest.skipUnless(os.name == 'posix', 'Requires POSIX pseudo-terminals')
class UsbSimulation(unittest.TestCase):
    def test_two_serial_devices_and_report(self):
        import serial  # dependency check; PTYs use real pyserial
        del serial
        pairs = [pty.openpty(), pty.openpty()]
        masters = [p[0] for p in pairs]
        buffers = {fd: b'' for fd in masters}
        with tempfile.TemporaryDirectory() as output:
            proc = subprocess.Popen([sys.executable, str(ROOT/'tools/radio_test.py'),
                                     '--a', os.ttyname(pairs[0][1]),
                                     '--b', os.ttyname(pairs[1][1]), '--count', '1',
                                     '--version-a', 'l0-0.2', '--output', output], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 25
                while proc.poll() is None and time.monotonic() < deadline:
                    readable, _, _ = select.select(masters, [], [], .1)
                    for fd in readable:
                        buffers[fd] += os.read(fd, 4096)
                        while b'\n' in buffers[fd]:
                            line, buffers[fd] = buffers[fd].split(b'\n', 1)
                            index = masters.index(fd)
                            if line == b'INFO':
                                version = 'l0-0.2' if index == 0 else 'pair-0.1'
                                reply = f'INFO {version} DEVICE{index} 1 1 BOOT{index} 869.525 125 7 5 0 1.8\n'
                                os.write(fd, reply.encode())
                            elif line.startswith(b'TX '):
                                payload = line[3:]
                                os.write(fd, b'TX 0 '+payload+b'\n')
                                os.write(masters[1-index], b'RX -60 9 '+payload+b'\n')
                if proc.poll() is None:
                    proc.kill()
                stdout, stderr = proc.communicate(timeout=3)
                self.assertEqual(proc.returncode, 0, (stdout, stderr))
                reports = list(Path(output).glob('*.json'))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_text())
                self.assertTrue(report['completed'])
                self.assertFalse(report['passed']) # abbreviated trial cannot qualify
                self.assertEqual(report['received_unique'], {'A': 1, 'B': 1})
                self.assertEqual(report['issues'], [])
                self.assertTrue(list(Path(output).glob('*.jsonl')))
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait()
                for master, slave in pairs:
                    os.close(master); os.close(slave)

if __name__ == '__main__':
    unittest.main()
