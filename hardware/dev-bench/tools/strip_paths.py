# SPDX-License-Identifier: MIT
"""Replace this checkout's absolute path in generated files by a relative one."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in sys.argv[1:]:
    p = ROOT / name
    t = p.read_text(encoding='utf-8')
    p.write_text(t.replace(str(ROOT) + '/', ''), encoding='utf-8')
