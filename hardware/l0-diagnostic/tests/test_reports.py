"""Regression cases: never accept a truncated or internally consistent false report."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import diagnose

class FramReports(unittest.TestCase):
    def test_matching_but_wrong_crc_is_rejected(self):
        with self.assertRaises(RuntimeError):
            diagnose.validate_fram(['FRAM_PASS 4 0 00000000 00000000','FRAM_DONE 00000001 VERIFY'],1,True)

    def test_nonzero_error_count_is_rejected(self):
        with self.assertRaises(RuntimeError):
            diagnose.validate_fram([f'FRAM_PASS 4 1 {diagnose.expected_crc(4,1):08X} {diagnose.expected_crc(4,1):08X}','FRAM_DONE 00000001 VERIFY'],1,True)

    def test_duplicate_completion_is_rejected(self):
        with self.assertRaises(RuntimeError):
            diagnose.validate_fram([f'FRAM_PASS 4 0 {diagnose.expected_crc(4,1):08X} {diagnose.expected_crc(4,1):08X}','FRAM_DONE 00000001 VERIFY','FRAM_DONE 00000001 VERIFY'],1,True)

    def test_malformed_pass_is_reported_as_failure(self):
        with self.assertRaises(RuntimeError):
            diagnose.validate_fram(['FRAM_PASS x','FRAM_DONE 00000001 VERIFY'],1,True)

class CommandReports(unittest.TestCase):
    def test_command_injection_and_empty_ack_rejected(self):
        for command,end in [('STATUS\nGUARD ERASE','STATUS '),('STATUS',''),('STATUS','\n')]:
            with self.assertRaises(RuntimeError):diagnose.check_command(command,end)

    def test_radio_nan_and_malformed_ready_rejected(self):
        for line in ['RX nan 9 TEST','RX -60 inf TEST','INFO l0-0.5 ID 2 1 BOOT 869.525 125 7 5 0 1.8']:
            self.assertEqual(diagnose.radio_test.decode(line)['kind'],'error')

    def test_mixed_failure_attempts_stop(self):
        from unittest.mock import patch
        from argparse import Namespace
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(diagnose,'transact',side_effect=[{'node':{}},{}]) as transact:
                with patch.object(diagnose.radio_test,'run',return_value=1):
                    with self.assertRaises(RuntimeError):
                        diagnose.run_mixed(Namespace(port='L0',peer='R0'),Path(folder)/'session')
                self.assertEqual(transact.call_args_list[1].args[1],'STOP')

class MixedReports(unittest.TestCase):
    def test_rejects_short_stalled_or_malformed_mixed_trial(self):
        import json
        import tempfile
        cases = [
            {'node':'A','line':'MIX_DONE 4000 0 4000 899999 225','elapsed_s':895},
            {'node':'A','line':'MIX_DONE 4000 0 4000 900000 1001','elapsed_s':895},
            {'node':'A','line':'MIX_DONE 4000 0 4000 900000 225','elapsed_s':2},
            {'node':'A','line':'MIX_DONE 4000 0 3999 900000 225','elapsed_s':895},
            {'node':'A','line':None,'elapsed_s':895},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'raw.jsonl'
            for case in cases:
                path.write_text(json.dumps(case)+'\n')
                with self.subTest(case=case),self.assertRaises(RuntimeError):diagnose.validate_mixed(path)
