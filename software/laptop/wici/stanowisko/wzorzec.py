# SPDX-License-Identifier: MIT
"""The reference model of reception, used by the application as is.

docs/spec/stanowisko-osp.md, „Przyjęcie”: the schema and state transitions are those of the reference model
(software/reference: OSPStore, schema.sql), and the application uses this schema. Instead of a second copy,
the application loads reference.py itself: from the station package (stage S10 puts reference.py and
schema.sql next to this file) or, when run from the repository, from software/reference. The model has
its own acceptance tests (software/reference/test_reference.py).
"""

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CANDIDATES = (_HERE / "reference.py", _HERE.parents[2] / "reference" / "reference.py")


def _load():
    path = next((p for p in _CANDIDATES if p.is_file()), None)
    if path is None:
        raise ImportError("brak modelu wzorcowego (reference.py) obok aplikacji stanowiska ani w repozytorium")
    spec = importlib.util.spec_from_file_location("wici_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = _load()
OSPStore = reference.OSPStore
QuarantineFull = reference.QuarantineFull
decode_message = reference.decode_message
encode_message = reference.encode_message
QUARANTINE_PER_SENDER = reference.QUARANTINE_PER_SENDER
QUARANTINE_TOTAL = reference.QUARANTINE_TOTAL
