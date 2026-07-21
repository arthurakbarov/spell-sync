"""Tests for structured technical event logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from spell_sync.application.events import (
    EventCategory,
    EventEmitter,
    EventId,
    EventPhase,
    EventSeverity,
    OperationKind,
    TechnicalEvent,
)
from spell_sync.diagnostics.technical_event_log import (
    SCHEMA_VERSION,
    format_log_line_for_display,
    parse_technical_log_line,
    serialize_technical_event,
    technical_event_to_dict,
    write_technical_event,
)
from spell_sync.diagnostics.technical_logging import reset_logging_for_tests


def _sample_event(**kwargs) -> TechnicalEvent:
    defaults = dict(
        event_id=EventId.PUSH_PLAN_VERIFIED,
        operation=OperationKind.PUSH,
        category=EventCategory.LIFECYCLE,
        severity=EventSeverity.SUCCESS,
        phase=EventPhase.EXECUTING,
        correlation_id="plan-12345678",
        target_id="chrome",
    )
    defaults.update(kwargs)
    return TechnicalEvent(**defaults)


def setup_function() -> None:
    reset_logging_for_tests()


def teardown_function() -> None:
    reset_logging_for_tests()


def test_technical_event_to_dict_serializes_enums_and_optional_fields() -> None:
    when = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    payload = technical_event_to_dict(_sample_event(), timestamp=when)
    assert payload == {
        "schemaVersion": SCHEMA_VERSION,
        "timestamp": "2026-07-21T12:00:00Z",
        "eventId": "push.plan_verified",
        "operation": "push",
        "category": "lifecycle",
        "severity": "success",
        "phase": "executing",
        "correlationId": "plan-12345678",
        "targetId": "chrome",
    }


def test_serialize_technical_event_is_sorted_json() -> None:
    line = serialize_technical_event(_sample_event())
    parsed = json.loads(line)
    assert line == json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    assert parsed["eventId"] == "push.plan_verified"


def test_parse_technical_log_line_accepts_structured_json() -> None:
    line = serialize_technical_event(_sample_event())
    parsed = parse_technical_log_line(line)
    assert parsed is not None
    assert parsed["eventId"] == "push.plan_verified"


def test_parse_technical_log_line_returns_none_for_legacy_text() -> None:
    assert parse_technical_log_line("2026-07-21 push started") is None
    assert parse_technical_log_line("push started") is None


def test_parse_technical_log_line_returns_none_for_malformed_json() -> None:
    assert parse_technical_log_line("{not-json") is None
    assert parse_technical_log_line('{"schemaVersion":99}') is None
    assert parse_technical_log_line('{"schemaVersion":1,"eventId":"unknown.event"}') is None
    assert parse_technical_log_line('{"schemaVersion":1,"eventId":1}') is None


def test_format_log_line_for_display_handles_structured_and_legacy_lines() -> None:
    structured = serialize_technical_event(_sample_event())
    assert "push.plan_verified" in format_log_line_for_display(structured)
    legacy = "removed words: [secret-token-value]"
    formatted = format_log_line_for_display(legacy)
    assert "secret-token-value" not in formatted


def test_write_technical_event_logs_structured_line(tmp_path, monkeypatch) -> None:
    from spell_sync.diagnostics.paths import resolve_app_state_paths
    from spell_sync.diagnostics.technical_logging import (
        configure_file_logging,
        read_technical_log_tail,
    )

    paths = resolve_app_state_paths(state_root=tmp_path / "state")
    configure_file_logging(paths)
    write_technical_event(_sample_event())
    snapshot = read_technical_log_tail(paths)
    assert any('"eventId":"push.plan_verified"' in line.replace(" ", "") for line in snapshot.lines)


def test_event_emitter_is_fail_open_when_sink_raises() -> None:
    seen: list[str] = []

    def failing_technical(_event: TechnicalEvent) -> None:
        raise RuntimeError("technical sink failed")

    def presentation(event) -> None:
        seen.append(event.event_id.value)

    emitter = EventEmitter(presentation_sink=presentation, technical_sink=failing_technical)
    emitter.emit(_sample_event())
    assert seen == ["push.plan_verified"]

    def failing_presentation(_event) -> None:
        raise RuntimeError("presentation sink failed")

    emitter = EventEmitter(
        presentation_sink=failing_presentation,
        technical_sink=lambda _event: seen.append("technical"),
    )
    emitter.emit(_sample_event())
    assert "technical" in seen


def test_technical_event_to_dict_rejects_forbidden_payload_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        "spell_sync.diagnostics.technical_event_log._FORBIDDEN_PAYLOAD_KEYS",
        frozenset({"severity"}),
    )
    try:
        technical_event_to_dict(_sample_event())
    except ValueError as exc:
        assert "forbidden technical event field" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_technical_log_line_returns_none_for_non_object_json() -> None:
    assert parse_technical_log_line('"hello"') is None


def test_format_log_line_for_display_omits_target_suffix_when_missing() -> None:
    event = _sample_event(target_id=None)
    line = serialize_technical_event(event)
    formatted = format_log_line_for_display(line)
    assert "target=" not in formatted
    assert "push.plan_verified" in formatted
