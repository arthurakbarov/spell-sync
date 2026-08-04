"""CLI import path stays free of Textual until UI launch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_import_does_not_load_textual() -> None:
    script = """
import sys
import spell_sync.cli  # noqa: F401
loaded = [name for name in sys.modules if name == "textual" or name.startswith("textual.")]
assert not loaded, loaded
assert "spell_sync.tui.launch" not in sys.modules
assert "spell_sync.tui.app" not in sys.modules
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok" in proc.stdout
