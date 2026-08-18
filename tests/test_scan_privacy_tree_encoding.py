"""Privacy scan must not skip non-UTF-8 text files."""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "scripts" / "scan_privacy_tree.py"

_spec = importlib.util.spec_from_file_location("scan_privacy_tree", MOD_PATH)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["scan_privacy_tree"] = mod
_spec.loader.exec_module(mod)


def test_latin1_home_path_is_detected(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    leaked = tmp_path / "notes.txt"
    # Build path at runtime so this test file itself does not trip the scanner.
    home = f"/Users/{mod.AUTHOR_LOGIN}/code/secret"
    leaked.write_bytes((home + " caf\xe9\n").encode("latin-1"))
    subprocess.run(["git", "add", "notes.txt"], cwd=tmp_path, check=True, capture_output=True)
    hits = mod.scan_privacy_tree(tmp_path)
    assert any(h.category == "personal-home-path" for h in hits)
