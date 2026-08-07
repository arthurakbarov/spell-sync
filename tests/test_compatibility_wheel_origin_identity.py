"""Wheel origin probe must stay inside temporary venv and outside checkout."""

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


def test_global_site_packages_origin_rejected(tmp_path: Path) -> None:
    mod = _load_compat_mod()
    venv = tmp_path / "venv"
    venv.mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    probe = {
        "origin": "/opt/global/site-packages/spell_sync/__init__.py",
        "executable": str(venv / "bin" / "python"),
        "sysPrefix": str(venv),
        "basePrefix": str(venv),
        "purelib": str(venv / "lib/python3.12/site-packages"),
        "platlib": str(venv / "lib/python3.12/site-packages"),
        "version": "1.0.0",
    }
    assert (
        mod._validate_wheel_origin_probe(probe, venv_dir=venv, checkout_root=checkout)
        == "compatibility.wheel-origin-failed"
    )


def test_wrong_sys_prefix_rejected(tmp_path: Path) -> None:
    mod = _load_compat_mod()
    venv = tmp_path / "venv"
    site = venv / "lib/python3.12/site-packages"
    origin = site / "spell_sync" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("# stub\n", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    probe = {
        "origin": str(origin),
        "executable": str(venv / "bin" / "python"),
        "sysPrefix": "/tmp/other-venv",
        "basePrefix": "/tmp/other-venv",
        "purelib": str(site),
        "platlib": str(site),
        "version": "1.0.0",
    }
    assert (
        mod._validate_wheel_origin_probe(probe, venv_dir=venv, checkout_root=checkout)
        == "compatibility.wheel-origin-failed"
    )


def test_origin_outside_purelib_rejected(tmp_path: Path) -> None:
    mod = _load_compat_mod()
    venv = tmp_path / "venv"
    site = venv / "lib/python3.12/site-packages"
    site.mkdir(parents=True)
    origin = venv / "outside" / "spell_sync" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("# stub\n", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    probe = {
        "origin": str(origin),
        "executable": str(venv / "bin" / "python"),
        "sysPrefix": str(venv),
        "basePrefix": str(venv),
        "purelib": str(site),
        "platlib": str(site),
        "version": "1.0.0",
    }
    assert (
        mod._validate_wheel_origin_probe(probe, venv_dir=venv, checkout_root=checkout)
        == "compatibility.wheel-origin-failed"
    )


def test_temporary_venv_origin_accepted(tmp_path: Path) -> None:
    mod = _load_compat_mod()
    venv = tmp_path / "venv"
    site = venv / "lib/python3.12/site-packages"
    origin = site / "spell_sync" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("# stub\n", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    probe = {
        "origin": str(origin),
        "executable": str(venv / "bin" / "python"),
        "sysPrefix": str(venv),
        "basePrefix": str(venv),
        "purelib": str(site),
        "platlib": str(site),
        "version": "1.0.0",
    }
    assert mod._validate_wheel_origin_probe(probe, venv_dir=venv, checkout_root=checkout) is None
    assert not mod._path_within(origin, checkout)


@pytest.mark.skipif(
    not (ROOT / "pyproject.toml").is_file(),
    reason="requires project root",
)
def test_wheel_compatibility_origin_inside_venv_outside_checkout() -> None:
    mod = _load_compat_mod()
    results, rc, failed = mod._run_wheel_compatibility(sys.executable)
    assert rc == 0, failed
    assert any(item["step"] == "compatibility.wheel-origin" for item in results)
