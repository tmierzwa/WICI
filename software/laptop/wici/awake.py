# SPDX-License-Identifier: MIT
"""Keep the laptop from sleeping while the application runs (docs/spec/oprogramowanie.md, "Pakiet USB").

Windows: SetThreadExecutionState. macOS: caffeinate bound to this process. Linux: systemd-inhibit while
it exists. Failure is not an error: the station works without the laptop and the panel reconnects.
"""

import os
import shutil
import subprocess
import sys


class Awake:
    def __init__(self):
        self.proc = None
        try:
            if sys.platform == "win32":
                import ctypes
                # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: nie usypiaj, ekran może zgasnąć
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
            elif sys.platform == "darwin" and shutil.which("caffeinate"):
                self.proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
            elif shutil.which("systemd-inhibit"):
                self.proc = subprocess.Popen(["systemd-inhibit", "--what=sleep:idle", "--who=WICI",
                                              "--why=Panel stacji WICI", "--mode=block", "sh", "-c",
                                              # blokada znika razem z aplikacją, także po jej zabiciu
                                              f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 5; done"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.proc = None

    def release(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except OSError:
                pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
