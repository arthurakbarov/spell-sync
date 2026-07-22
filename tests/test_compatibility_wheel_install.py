"""Compatibility runner installs wheel into isolated venv outside checkout."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_compat_mod():
    spec = importlib.util.spec_from_file_location(
        "run_compatibility_checks",
        ROOT / "scripts" / "run_compatibility_checks.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not (ROOT / "pyproject.toml").is_file(),
    reason="requires project root",
)
def test_wheel_compatibility_steps_succeed() -> None:
    mod = _load_compat_mod()
    results, rc, failed = mod._run_wheel_compatibility(sys.executable)
    step_ids = [item["step"] for item in results]
    assert "compatibility.wheel-build" in step_ids
    assert "compatibility.wheel-install" in step_ids
    assert "compatibility.wheel-origin" in step_ids
    assert rc == 0, failed
