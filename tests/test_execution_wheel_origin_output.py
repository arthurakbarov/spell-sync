"""Wheel origin functional output must not depend on sanitized retained evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.ci_runner import (  # noqa: E402
    _read_wheel_origin_result,
    _verify_wheel_origin,
)
from scripts.execution_control.privacy import sanitize_text, workspace_roots  # noqa: E402


@pytest.fixture
def private_home(tmp_path):
    home = tmp_path / "private-home"
    home.mkdir()
    return home


def test_sanitized_path_does_not_change_wheel_origin_decision(private_home, tmp_path):
    origin_file = private_home / "smoke-venv/lib/python3.11/site-packages/spell_sync/__init__.py"
    origin_file.parent.mkdir(parents=True, exist_ok=True)
    origin_file.write_text("# wheel\n", encoding="utf-8")
    venv_dir = private_home / "smoke-venv"
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    raw_origin = str(origin_file.resolve())
    assert str(private_home.resolve()) in raw_origin

    ok_raw, _ = _verify_wheel_origin(origin_file, venv_dir=venv_dir, root=checkout)
    assert ok_raw is True

    sanitized = sanitize_text(
        raw_origin,
        home=private_home,
        workspace_roots=workspace_roots(public_root=checkout),
    )
    assert "[HOME]" in sanitized or "[WORKSPACE]" in sanitized
    assert private_home.as_posix() not in sanitized

    sanitized_path = Path(sanitized)
    ok_sanitized, _ = _verify_wheel_origin(sanitized_path, venv_dir=venv_dir, root=checkout)
    assert ok_sanitized is False


def test_wheel_origin_json_read_before_retained_sanitization(private_home, tmp_path):
    checkout = ROOT
    venv_dir = private_home / "isolated-venv"
    origin_file = venv_dir / "lib/python3.11/site-packages/spell_sync/__init__.py"
    origin_file.parent.mkdir(parents=True, exist_ok=True)
    origin_file.write_text("# installed wheel\n", encoding="utf-8")

    result_path = tmp_path / "wheel-origin.json"
    payload = {
        "origin": str(origin_file.resolve()),
        "metadataVersion": "1.0.0",
        "sysPrefix": str(venv_dir.resolve()),
        "basePrefix": str(venv_dir.resolve()),
        "sysExecutable": str(venv_dir / "bin" / "python"),
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    origin_path, metadata_version, diagnostics = _read_wheel_origin_result(result_path)
    ok, detail = _verify_wheel_origin(origin_path, venv_dir=venv_dir, root=checkout)
    assert ok, detail
    assert metadata_version == "1.0.0"
    assert str(venv_dir.resolve()) in diagnostics["sysPrefix"]

    retained = sanitize_text(
        json.dumps({"origin": str(origin_path), "detail": detail, "diagnostics": diagnostics}),
        home=private_home,
        workspace_roots=workspace_roots(public_root=checkout),
    )
    assert str(private_home) not in retained
    assert str(origin_path.resolve()) not in retained

    result_path.unlink(missing_ok=True)
