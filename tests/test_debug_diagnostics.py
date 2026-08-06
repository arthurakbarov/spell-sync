"""Privacy-safe unexpected-error boundaries and debug diagnostics."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from spell_sync.application.events import EventEmitter
from spell_sync.application.requests import ProjectRef
from spell_sync.application.services.inspection import InspectionService
from spell_sync.diagnostics.debug_mode import (
    debug_diagnostics_enabled,
    emit_debug_traceback,
    unexpected_error_category,
)
from spell_sync.diagnostics.technical_event_model import (
    EventCategory,
    EventId,
    EventSeverity,
    OperationKind,
    TechnicalEvent,
)
from spell_sync.tui import launch as launch_mod


SENSITIVE = "SECRET_WORDLIST_TOKEN_xyz"


def _sample_event() -> TechnicalEvent:
    return TechnicalEvent(
        event_id=EventId.PULL_COMPLETED,
        operation=OperationKind.PULL,
        category=EventCategory.DIAGNOSTIC,
        severity=EventSeverity.ERROR,
    )


def test_debug_diagnostics_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    assert debug_diagnostics_enabled() is False


def test_debug_traceback_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    buf = io.StringIO()
    emit_debug_traceback(RuntimeError(SENSITIVE), stream=buf)
    assert buf.getvalue() == ""
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    buf2 = io.StringIO()
    try:
        raise RuntimeError(SENSITIVE)
    except RuntimeError as exc:
        emit_debug_traceback(exc, stream=buf2)
    text = buf2.getvalue()
    assert "RuntimeError" in text
    assert SENSITIVE in text  # stderr debug may include message; stdout must not


def test_unexpected_error_category_is_type_only() -> None:
    assert unexpected_error_category(RuntimeError(SENSITIVE)) == "RuntimeError"


def test_event_emitter_fail_open_suppresses_sink_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)

    def boom(_event: TechnicalEvent) -> None:
        raise OSError(SENSITIVE)

    emitter = EventEmitter(presentation_sink=None, technical_sink=boom)
    emitter.emit(_sample_event())
    out = capsys.readouterr()
    assert SENSITIVE not in out.out
    assert SENSITIVE not in out.err


def test_event_emitter_debug_shows_sink_failure_on_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")

    def boom(_event: TechnicalEvent) -> None:
        raise OSError("sink-failed")

    emitter = EventEmitter(presentation_sink=None, technical_sink=boom)
    emitter.emit(_sample_event())
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "OSError" in captured.err
    assert "sink-failed" in captured.err


def test_run_ui_unexpected_stays_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)

    def raise_sensitive(*_a, **_k):
        raise KeyError(SENSITIVE)

    monkeypatch.setattr(launch_mod, "TuiController", raise_sensitive)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "TUI failed to start" in captured.out


def test_run_ui_debug_traceback_on_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")

    def raise_sensitive(*_a, **_k):
        raise KeyError(SENSITIVE)

    monkeypatch.setattr(launch_mod, "TuiController", raise_sensitive)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "KeyError" in captured.err


def test_load_doctor_expected_error_stable_message() -> None:
    ctx = MagicMock()
    ctx.runtime.sync_run.side_effect = OSError("disk full")
    service = InspectionService(ctx, MagicMock())
    snap = service.load_doctor(MagicMock())
    assert snap.has_errors is True
    assert snap.load_error == "Doctor report could not be loaded."


def test_load_doctor_unexpected_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    ctx = MagicMock()
    ctx.runtime.sync_run.side_effect = AssertionError(SENSITIVE)
    service = InspectionService(ctx, MagicMock())
    snap = service.load_doctor(MagicMock())
    assert snap.load_error == "Doctor report could not be loaded."
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in json.dumps({"load_error": snap.load_error})
