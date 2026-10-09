"""Real pyserial over PTY; never evidence of physical USB, FRAM or RF."""
import json
import os
import pty
import select
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import diagnose


@unittest.skipUnless(os.name == 'posix', 'POSIX PTY required')
class UsbChecks(unittest.TestCase):
    def exercise(self, *, version='l0-0.3', response=None, success=True, ready=1,
                 command='FRAMVERIFY 00000001', end='FRAM_DONE ', validate=True):
        master, slave = pty.openpty()
        stop = threading.Event()
        commands = []
        crc = diagnose.expected_crc(4, 1)
        if response is None:
            response = f'FRAM_PASS 4 0 {crc:08X} {crc:08X}\nFRAM_DONE 00000001 VERIFY\n'

        def device():
            buffer = b''
            while not stop.is_set():
                if not select.select([master], [], [], .05)[0]:
                    continue
                buffer += os.read(master, 4096)
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    commands.append(line)
                    if line == b'INFO':
                        os.write(master, f'CMD INFO\nINFO {version} L0SIM {ready} 1 BOOT 869.525 125 7 5 0 1.8\n'.encode())
                    elif line.decode() == command:
                        os.write(master, ('CMD ' + command + '\n' + response).encode())

        worker = threading.Thread(target=device)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'result.json'
                validator = (lambda lines: diagnose.validate_fram(lines, 1, True)) if validate else None
                if success:
                    report = diagnose.transact(os.ttyname(slave), command, end, .3, output,
                                               validator=validator)
                    self.assertTrue(report['software_command_completed'])
                else:
                    with self.assertRaises(RuntimeError):
                        diagnose.transact(os.ttyname(slave), command, end, .3, output, validator=validator)
                report = json.loads(output.read_text())
                self.assertEqual(report['software_command_completed'], success)
                self.assertFalse(report['physical_acceptance'])
                if version != 'l0-0.3':
                    self.assertNotIn(command.encode(), commands)
                if not success:
                    self.assertIn('error', report)
                return report
        finally:
            stop.set()
            worker.join(timeout=2)
            os.close(master)
            os.close(slave)

    def test_retention_real_serial(self):
        self.exercise()

    def test_wrong_image_blocks_command(self):
        self.exercise(version='pair-0.2', success=False)

    def test_failed_crc_never_writes_success_report(self):
        self.exercise(response='FRAM_PASS 4 0 00000000 00000000\nFRAM_DONE 00000001 VERIFY\n', success=False)

    def test_missing_completion_retains_failed_log(self):
        report = self.exercise(response='FRAM_PASS 4 0 00000000 00000000\n', success=False)
        self.assertTrue(any(line.startswith('FRAM_PASS') for line in report['records']))

    def test_restart_during_command_is_rejected(self):
        self.exercise(response='INFO l0-0.3 L0SIM 1 1 NEWBOOT 869.525 125 7 5 0 1.8\n', success=False)

    def test_status_can_diagnose_not_ready_board(self):
        self.exercise(ready=0, command='STATUS', end='STATUS ', validate=False,
                      response='STATUS radio=0 fram=1 ext=1\n')

    def test_blocked_tx_fails_without_waiting_for_timeout(self):
        self.exercise(command='TX TEST', end='TX ', validate=False, success=False,
                      response='BLOCKED SILENCE\n')
