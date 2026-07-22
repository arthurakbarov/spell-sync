"""Pytest: repository root on sys.path and shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

from spell_sync.cli_options import CliOptions

pytest_plugins = ["conftest_execution"]

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

DEFAULT_OPTS = CliOptions()
