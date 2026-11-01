# SPDX-License-Identifier: MIT
"""Reference entry point for the packaged WICI envelope implementation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laptop"))
from wici.envelope import *  # noqa: F401,F403 - public codec API used by the reference tests
from wici.envelope import _nonce  # test of the nonce separation between fragments
