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


def test_presentation_sink_fail_open_keeps_technical_delivery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    seen: list[TechnicalEvent] = []

    def technical(event: TechnicalEvent) -> None:
        seen.append(event)

    def presentation(_event: object) -> None:
        raise RuntimeError(SENSITIVE)

    recorded: list[TechnicalEvent] = []

    def fake_write(event: TechnicalEvent) -> None:
        recorded.append(event)

    monkeypatch.setattr(
        "spell_sync.diagnostics.technical_event_log.write_technical_event",
        fake_write,
    )
    emitter = EventEmitter(presentation_sink=presentation, technical_sink=technical)
    original = _sample_event()
    emitter.emit(original)
    assert seen == [original]
    assert any(
        event.event_id is EventId.DIAGNOSTICS_PRESENTATION_SINK_FAILED for event in recorded
    )
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err


def test_presentation_sink_debug_traceback_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    monkeypatch.setattr(
        "spell_sync.diagnostics.technical_event_log.write_technical_event",
        lambda _event: None,
    )
    emitter = EventEmitter(
        presentation_sink=lambda _e: (_ for _ in ()).throw(RuntimeError(SENSITIVE)),
        technical_sink=lambda _e: None,
    )
    emitter.emit(_sample_event())
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "RuntimeError" in captured.err
    assert SENSITIVE in captured.err


def test_run_ui_runtime_error_debug_off_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    events: list[EventId] = []

    def capture_event(event_id: EventId, **_kwargs) -> None:
        events.append(event_id)

    monkeypatch.setattr(launch_mod, "emit_boundary_technical_event", capture_event)
    monkeypatch.setattr(
        launch_mod,
        "_run_ui_impl",
        lambda _project: (_ for _ in ()).throw(RuntimeError(SENSITIVE)),
    )
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err
    assert "TUI failed to start" in captured.out
    assert EventId.DIAGNOSTICS_TUI_LAUNCH_UNEXPECTED_FAILURE in events


def test_run_ui_runtime_error_debug_on_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    monkeypatch.setattr(launch_mod, "emit_boundary_technical_event", lambda *_a, **_k: None)
    monkeypatch.setattr(
        launch_mod,
        "_run_ui_impl",
        lambda _project: (_ for _ in ()).throw(RuntimeError(SENSITIVE)),
    )
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "RuntimeError" in captured.err
    assert SENSITIVE in captured.err


def test_run_ui_value_error_debug_off_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    monkeypatch.setattr(launch_mod, "emit_boundary_technical_event", lambda *_a, **_k: None)
    monkeypatch.setattr(
        launch_mod,
        "_run_ui_impl",
        lambda _project: (_ for _ in ()).throw(ValueError(SENSITIVE)),
    )
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err
    assert "TUI failed to start" in captured.out


def test_run_ui_oserror_expected_no_debug_leak(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    events: list[EventId] = []

    def capture_event(event_id: EventId, **_kwargs) -> None:
        events.append(event_id)

    monkeypatch.setattr(launch_mod, "emit_boundary_technical_event", capture_event)
    monkeypatch.setattr(
        launch_mod,
        "_run_ui_impl",
        lambda _project: (_ for _ in ()).throw(OSError(SENSITIVE)),
    )
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err
    assert "TUI failed to start" in captured.out
    assert events == []


def test_run_ui_unexpected_stays_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )

    def raise_sensitive(*_a, **_k):
        raise KeyError(SENSITIVE)

    monkeypatch.setattr(launch_mod, "_run_ui_impl", raise_sensitive)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "TUI failed to start" in captured.out


def test_run_ui_debug_traceback_on_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )

    def raise_sensitive(*_a, **_k):
        raise KeyError(SENSITIVE)

    monkeypatch.setattr(launch_mod, "_run_ui_impl", raise_sensitive)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "KeyError" in captured.err


def test_run_ui_import_error_privacy_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )

    def boom(_project: ProjectRef) -> int:
        raise ImportError(f"No module named textual ({SENSITIVE})")

    monkeypatch.setattr(launch_mod, "_run_ui_impl", boom)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err
    assert "TUI failed to start" in captured.out
    assert "textual" not in captured.out.lower()


def test_run_ui_import_error_debug_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )

    def boom(_project: ProjectRef) -> int:
        raise ImportError(f"No module named textual ({SENSITIVE})")

    monkeypatch.setattr(launch_mod, "_run_ui_impl", boom)
    code = launch_mod.run_ui(ProjectRef())
    assert code == 1
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "ImportError" in captured.err
    assert SENSITIVE in captured.err


def test_load_doctor_expected_oserror_stable_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    ctx = MagicMock()
    ctx.runtime.sync_run.side_effect = OSError(SENSITIVE)
    service = InspectionService(ctx, MagicMock())
    snap = service.load_doctor(MagicMock())
    assert snap.has_errors is True
    assert snap.load_error == "Doctor report could not be loaded."
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err


@pytest.mark.parametrize("exc_factory", [lambda: TypeError(SENSITIVE), lambda: KeyError(SENSITIVE)])
def test_load_doctor_unexpected_programming_error_privacy_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exc_factory,
) -> None:
    monkeypatch.delenv("SPELL_SYNC_DEBUG", raising=False)
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )
    ctx = MagicMock()
    ctx.runtime.sync_run.side_effect = exc_factory()
    service = InspectionService(ctx, MagicMock())
    snap = service.load_doctor(MagicMock())
    assert snap.load_error == "Doctor report could not be loaded."
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert SENSITIVE not in captured.err
    assert SENSITIVE not in json.dumps({"load_error": snap.load_error})


def test_load_doctor_unexpected_debug_stderr_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SPELL_SYNC_DEBUG", "1")
    monkeypatch.setattr(
        "spell_sync.diagnostics.debug_mode.emit_boundary_technical_event",
        lambda *_a, **_k: None,
    )
    ctx = MagicMock()
    ctx.runtime.sync_run.side_effect = TypeError(SENSITIVE)
    service = InspectionService(ctx, MagicMock())
    snap = service.load_doctor(MagicMock())
    assert snap.load_error == "Doctor report could not be loaded."
    captured = capsys.readouterr()
    assert SENSITIVE not in captured.out
    assert "TypeError" in captured.err
    assert SENSITIVE in captured.err
