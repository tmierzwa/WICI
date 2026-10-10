"""Actual firmware/driver control flow with virtual SPI/GPIO/time/RF; not physical evidence."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import diagnose

class FirmwareNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.binary=Path(cls.folder.name)/'firmware-test'
        subprocess.run(['clang++','-std=c++11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                        '-I'+str(ROOT/'tests/native'),'-I'+str(ROOT/'src'),
                        str(ROOT/'tests/native/firmware_test.cpp'),
                        *[str(ROOT/'src'/name) for name in ('fram.cpp','sharp.cpp','font.cpp')],
                        '-o',str(cls.binary)],check=True)
    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()
    def run_case(self,name):
        result=subprocess.run([str(self.binary),name],check=True,capture_output=True,text=True,timeout=45)
        return result.stdout.splitlines()
    def test_boot_is_read_only_and_selects_safe(self):self.run_case('boot')
    def test_actual_spi_fram_and_retention_crc(self):
        diagnose.validate_fram(self.run_case('fram')[1:],1,False)
    def test_guard_exclusive_bus_and_stop(self):self.run_case('guard')
    def test_full_mixed_duration_rollover_and_pause_block(self):
        lines=self.run_case('mixed')
        self.assertEqual(lines,['MIX_DONE 4500 0 4500 900000 400'])
    def test_usb_overflow_nul_and_seed_rejection(self):self.run_case('usb')
    def test_silence_cooldown_and_embedded_nul_rx(self):self.run_case('radio')
    def test_lcd_timer_failure_keeps_disp_low(self):self.run_case('lcd-failure')
    def test_mb85rs4mt_alternative_accepted(self):self.run_case('boot-mb85rs4mt')
    def test_unsupported_fram_blocks_tests(self):self.run_case('fram-unsupported')

    @unittest.skipUnless(sys.platform == 'darwin' or sys.platform.startswith('linux'), 'POSIX PTY required')
    def test_firmware_to_host_over_real_serial(self):
        import os
        import pty
        import select
        import threading
        import tty
        master, slave = pty.openpty()
        tty.setraw(slave)
        stop = threading.Event()
        process = subprocess.Popen([str(self.binary), 'console'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def bridge():
            while not stop.is_set():
                readable, _, _ = select.select([master, process.stdout.fileno()], [], [], .05)
                for fd in readable:
                    data = os.read(fd, 4096)
                    if not data:
                        return
                    if fd == master:
                        process.stdin.write(data)
                        process.stdin.flush()
                    else:
                        os.write(master, data)
        worker = threading.Thread(target=bridge)
        worker.start()
        try:
            for verify in (False, True):
                command = ('FRAMVERIFY ' if verify else 'FRAMTEST ERASE ') + '00000001'
                report = diagnose.transact(os.ttyname(slave), command, 'FRAM_DONE ', 10,
                                           Path(self.folder.name) / ('read.json' if verify else 'write.json'),
                                           validator=lambda lines: diagnose.validate_fram(lines, 1, verify))
                self.assertTrue(report['software_command_completed'])
                self.assertFalse(report['physical_acceptance'])
        finally:
            stop.set()
            worker.join(timeout=2)
            process.stdin.close()
            process.wait(timeout=3)
            error = process.stderr.read().decode()
            process.stdout.close()
            process.stderr.close()
            os.close(master)
            os.close(slave)
            self.assertEqual(process.returncode, 0, error)
