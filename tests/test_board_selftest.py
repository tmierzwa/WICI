# SPDX-License-Identifier: MIT
"""Summary of the core self-test on a board (firmware/tools/board_selftest.py) from console lines.

The console part needs a board; this checks only how the tool reads the JSON lines of `RNS SELFTEST`
and `LOG` (firmware/src/main.cpp, printSelftest and Bench::printLog).

  python3 -m unittest tests.test_board_selftest
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tools"))
import board_selftest  # noqa: E402


class SummaryTests(unittest.TestCase):
    def test_runs_and_median(self):
        lines = ['{"contract":2,"rns_state":"running","entropy_ok":true}', "śmieci",
                 '{"log":[{"seq":2,"uptime_s":1,"text":"core selftest ok 1480 ms"},{"seq":3,"uptime_s":1,"text":"rns started"}],'
                 '"total":3,"fram":true}']
        for us in (100, 300, 200):
            lines += [f'{{"selftest":"sign","ok":true,"us":{us}}}', '{"selftest":"validate","ok":true,"us":5}',
                      '{"selftest_ok":true,"entropy_ok":true,"version":"bench-a-0.1"}']
        s = board_selftest.summarize(lines)
        self.assertEqual((s["ok"], s["runs"], s["entropy_ok"], s["rns_state"], s["version"], s["startup_selftest_ms"]),
                         (True, [True] * 3, True, "running", "bench-a-0.1", 1480))
        self.assertEqual(s["checks"]["sign"], {"ok": True, "us_median": 200, "us": [100, 300, 200]})
        self.assertEqual(s["log"], ["core selftest ok 1480 ms", "rns started"])

    def test_mismatch_and_failed_start(self):
        lines = ['{"log":[{"ms":4,"text":"entropy source failed health test"},'
                 '{"ms":5,"text":"rns not started: core selftest token_decrypt failed"}]}',
                 '{"contract":2,"rns_state":"selftest_failed","entropy_ok":false}',
                 '{"selftest":"token_decrypt","ok":false,"us":9}', '{"selftest_ok":false,"entropy_ok":false,"version":"l0-0.2"}']
        s = board_selftest.summarize(lines)
        self.assertFalse(s["ok"])
        self.assertFalse(s["checks"]["token_decrypt"]["ok"])
        self.assertEqual((s["rns_state"], s["startup_selftest_ms"]), ("selftest_failed", None))
        self.assertEqual(s["log"], ["entropy source failed health test", "rns not started: core selftest token_decrypt failed"])

    def test_no_selftest_output(self):
        self.assertFalse(board_selftest.summarize(['{"error":"unknown command"}'])["ok"])


if __name__ == "__main__":
    unittest.main()
