"""Tests for packaged target validation metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from spell_sync.application.target_details import build_target_details
from spell_sync.project_setup.discovery import SetupTarget
from spell_sync.target_validation import load_packaged_target_validation


def _target(identifier: str = "chrome") -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path("/tmp/dict.txt"),
        format_name="text",
        detected=True,
        available=True,
        readable=True,
        supported=True,
        enabled_by_default=True,
        selectable=True,
        word_count=1,
        status="ok",
        detail=None,
        enabled=True,
    )


def test_packaged_validation_json_exists() -> None:
    bundled = (
        Path(__file__).resolve().parents[1] / "spell_sync" / "bundled" / "target-validation.json"
    )
    assert bundled.is_file()


def test_load_packaged_target_validation_returns_entries() -> None:
    payload = load_packaged_target_validation()
    assert payload is not None
    assert isinstance(payload.get("targets"), list)
    assert payload["targets"]


def test_target_details_uses_packaged_automated_pass() -> None:
    details = build_target_details(_target("chrome"))
    assert details.automated_validation == "pass"
    assert details.manual_validation == "not-run"


def test_target_details_empty_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: None,
    )
    details = build_target_details(_target("chrome"))
    assert details.automated_validation == "not-run"
    assert details.manual_validation == "not-run"


def test_target_details_does_not_read_repository_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def loader() -> dict[str, object]:
        calls["count"] += 1
        return load_packaged_target_validation() or {"schema_version": 1, "targets": []}

    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        loader,
    )
    details = build_target_details(_target("chrome"))
    assert calls["count"] == 1
    assert details.automated_validation == "pass"
