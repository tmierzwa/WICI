#!/usr/bin/env python3
"""L0 uses the same radio runner as R0; delivery contains it in partner-r0/."""
import importlib.util
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_candidates = (
    _root.parent / 'radio-pair' / 'tools' / 'pair_test.py',
    _root / 'partner-r0' / 'tools' / 'pair_test.py',
)
_source = next((path for path in _candidates if path.is_file()), None)
if _source is None:
    raise ImportError('Brak wspólnego tools/pair_test.py: potrzebny radio-pair lub partner-r0 z paczki.')
_spec = importlib.util.spec_from_file_location('wici_pair_runner', _source)
_shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared)
PROFILE = _shared.PROFILE
L0_VERSION = _shared.L0_VERSION
decode = _shared.decode
judge = _shared.judge
open_serial = _shared.open_serial
run = _shared.run
main = _shared.main

if __name__ == '__main__':
    raise SystemExit(main())
