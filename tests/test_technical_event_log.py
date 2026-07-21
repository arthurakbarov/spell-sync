"""Tests for structured technical event logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from spell_sync.application.event_metadata import (
    CorrelationId,
    EventReason,
    TargetId,
    TerminalOutcome,
)
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
    ParsedTechnicalLogEvent,
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
        correlation_id=CorrelationId.parse("plan-12345678"),
        target_id=TargetId.parse("chrome"),
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
    assert isinstance(parsed, ParsedTechnicalLogEvent)
    assert parsed.event_id is EventId.PUSH_PLAN_VERIFIED


def test_parse_technical_log_line_returns_none_for_legacy_text() -> None:
    assert parse_technical_log_line("2026-07-21 push started") is None
    assert parse_technical_log_line("push started") is None


def test_parse_technical_log_line_returns_none_for_malformed_json() -> None:
    assert parse_technical_log_line("{not-json") is None
    assert parse_technical_log_line('{"schemaVersion":99}') is None
    assert parse_technical_log_line('{"schemaVersion":1,"eventId":"unknown.event"}') is None
    assert parse_technical_log_line('{"schemaVersion":1,"eventId":1}') is None
    assert (
        parse_technical_log_line(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "timestamp": "2026-07-21T12:00:00Z",
                    "eventId": "push.plan_verified",
                    "operation": "push",
                    "category": "lifecycle",
                    "severity": "success",
                    "correlationId": "bad id with spaces",
                }
            )
        )
        is None
    )


def test_format_log_line_for_display_handles_structured_and_legacy_lines() -> None:
    structured = serialize_technical_event(_sample_event())
    formatted = format_log_line_for_display(structured)
    assert "push.plan_verified" in formatted
    assert not formatted.strip().startswith("{")
    legacy = "removed words: [secret-token-value]"
    sanitized = format_log_line_for_display(legacy)
    assert "secret-token-value" not in sanitized


def test_format_log_line_for_display_redacts_malformed_json_sentinel() -> None:
    malformed = (
        '{"schemaVersion":1,"eventId":"push.plan_verified","operation":"push",'
        '"reasonCode":"SENSITIVE_USER_WORD_7f3a"}'
    )
    formatted = format_log_line_for_display(malformed)
    assert formatted == "[malformed structured log line]"
    assert "SENSITIVE_USER_WORD_7f3a" not in formatted


def test_target_id_parses_chrome_profile_with_space() -> None:
    parsed = TargetId.parse("chrome:Profile 1")
    assert parsed.value == "chrome:Profile 1"


def test_write_technical_event_end_to_end_jsonl_round_trip(tmp_path) -> None:
    from spell_sync.diagnostics.paths import resolve_app_state_paths
    from spell_sync.diagnostics.technical_logging import (
        configure_file_logging,
        read_technical_log_tail,
    )

    paths = resolve_app_state_paths(state_root=tmp_path / "state")
    configure_file_logging(paths)
    write_technical_event(_sample_event())
    raw_lines = paths.technical_log.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    raw_line = raw_lines[0]
    assert raw_line.startswith("{")
    assert raw_line.endswith("}")
    json.loads(raw_line)
    assert parse_technical_log_line(raw_line) is not None
    snapshot = read_technical_log_tail(paths)
    assert len(snapshot.lines) == 1
    assert "push.plan_verified" in snapshot.lines[0]
    assert raw_line not in snapshot.lines[0]


def test_read_technical_log_tail_handles_mixed_rotation_backup(tmp_path) -> None:
    from spell_sync.diagnostics.paths import resolve_app_state_paths
    from spell_sync.diagnostics.technical_logging import (
        BACKUP_COUNT,
        configure_file_logging,
        read_technical_log_tail,
    )

    paths = resolve_app_state_paths(state_root=tmp_path / "state")
    configure_file_logging(paths)
    legacy = "2026-07-21 INFO removed words: sentinel-value"
    structured = serialize_technical_event(_sample_event())
    malformed = '{"schemaVersion":1,"eventId":"push.plan_verified","operation":"push"}'
    paths.technical_log.parent.mkdir(parents=True, exist_ok=True)
    paths.technical_log.write_text(
        "\n".join((legacy, structured, malformed)) + "\n",
        encoding="utf-8",
    )
    backup = paths.technical_log.with_suffix(paths.technical_log.suffix + ".1")
    backup.write_text("rotated legacy line\n", encoding="utf-8")
    assert BACKUP_COUNT >= 1
    snapshot = read_technical_log_tail(paths)
    assert len(snapshot.lines) == 3
    assert all("sentinel-value" not in line for line in snapshot.lines)
    assert any("push.plan_verified" in line for line in snapshot.lines)


def test_event_emitter_technical_sink_fail_open_presentation_still_runs() -> None:
    seen: list[str] = []

    def failing_technical(_event: TechnicalEvent) -> None:
        raise RuntimeError("technical sink failed")

    def presentation(event) -> None:
        seen.append(event.event_id.value)

    emitter = EventEmitter(presentation_sink=presentation, technical_sink=failing_technical)
    emitter.emit(_sample_event())
    assert seen == ["push.plan_verified"]


def test_event_emitter_presentation_sink_exception_is_not_swallowed() -> None:
    def failing_presentation(_event) -> None:
        raise RuntimeError("presentation sink failed")

    emitter = EventEmitter(
        presentation_sink=failing_presentation,
        technical_sink=lambda _event: None,
    )
    with pytest.raises(RuntimeError, match="presentation sink failed"):
        emitter.emit(_sample_event())


def test_format_log_line_for_display_omits_target_suffix_when_missing() -> None:
    event = _sample_event(target_id=None)
    line = serialize_technical_event(event)
    formatted = format_log_line_for_display(line)
    assert "target=" not in formatted
    assert "push.plan_verified" in formatted


def test_parse_technical_log_line_returns_none_when_json_is_not_object(monkeypatch) -> None:
    import spell_sync.diagnostics.technical_event_log as technical_event_log

    def fake_loads(_line: str) -> list[int]:
        return [1, 2]

    monkeypatch.setattr(technical_event_log.json, "loads", fake_loads)
    assert technical_event_log.parse_technical_log_line('{"eventId":"push.completed"}') is None


def test_write_technical_event_fail_open_on_invalid_event() -> None:
    invalid = TechnicalEvent(
        event_id=EventId.PUSH_COMPLETED,
        operation=OperationKind.PUSH,
        category=EventCategory.LIFECYCLE,
        severity=EventSeverity.SUCCESS,
        correlation_id=CorrelationId.parse("ok-id"),
        completed=-1,
    )
    write_technical_event(invalid)


def test_structured_formatter_rejects_invalid_logger_message() -> None:
    from spell_sync.diagnostics.technical_event_log import validate_structured_log_message

    with pytest.raises(ValueError):
        validate_structured_log_message("not json")
    with pytest.raises(ValueError):
        validate_structured_log_message(
            json.dumps({"schemaVersion": 1, "eventId": "push.completed", "operation": "push"})
        )


def test_terminal_metadata_serializes_typed_reason_and_outcome() -> None:
    event = _sample_event(
        event_id=EventId.PUSH_FAILED,
        reason=EventReason.ROLLBACK_INCOMPLETE,
        outcome=TerminalOutcome.FAILED,
    )
    payload = technical_event_to_dict(event)
    assert payload["reasonCode"] == "rollback_incomplete"
    assert payload["outcome"] == "failed"


def test_event_helpers_parse_none_and_unknown_push_reason() -> None:
    from spell_sync.application.event_helpers import (
        parse_correlation,
        parse_target,
        push_abort_reason_to_event_reason,
    )

    assert parse_correlation(None) is None
    assert parse_target(None) is None
    assert push_abort_reason_to_event_reason(None) is None
    assert push_abort_reason_to_event_reason("unknown") is None


def test_correlation_rejects_whitespace_even_when_pattern_matches() -> None:
    with pytest.raises(ValueError):
        CorrelationId.parse("plan 123")


def test_validate_structured_log_message_rejects_invalid_payload() -> None:
    from spell_sync.diagnostics.technical_event_log import validate_structured_log_message

    with pytest.raises(ValueError, match="must be a JSON object"):
        validate_structured_log_message("plain text")
    with pytest.raises(ValueError, match="not valid JSON"):
        validate_structured_log_message("{bad-json}")
    with pytest.raises(ValueError, match="unexpected structured log keys"):
        validate_structured_log_message('{"schemaVersion":1,"extra":true}')
    with pytest.raises(ValueError, match="unsupported schemaVersion"):
        validate_structured_log_message('{"schemaVersion":99,"eventId":"push.completed"}')


def test_validate_parsed_dict_rejects_invalid_counts() -> None:
    from spell_sync.diagnostics.technical_event_log import _validate_parsed_dict

    base = {
        "schemaVersion": 1,
        "timestamp": "2026-07-21T12:00:00Z",
        "eventId": "push.completed",
        "operation": "push",
        "category": "lifecycle",
        "severity": "success",
        "completed": -1,
    }
    with pytest.raises(ValueError, match="invalid completed"):
        _validate_parsed_dict(base)
    base["completed"] = 2
    base["total"] = 1
    with pytest.raises(ValueError, match="completed exceeds total"):
        _validate_parsed_dict(base)


def test_enum_value_rejects_non_string_raw() -> None:
    from spell_sync.diagnostics.technical_event_log import _enum_value

    with pytest.raises(ValueError, match="invalid eventId type"):
        _enum_value(EventId, 1, "eventId")


def test_enum_value_rejects_unknown_member() -> None:
    from spell_sync.diagnostics.technical_event_log import _enum_value

    with pytest.raises(ValueError, match="invalid eventId"):
        _enum_value(EventId, "not.a.real.event", "eventId")


def test_validate_parsed_dict_rejects_invalid_total() -> None:
    from spell_sync.diagnostics.technical_event_log import _validate_parsed_dict

    payload = {
        "schemaVersion": 1,
        "timestamp": "2026-07-21T12:00:00Z",
        "eventId": "push.completed",
        "operation": "push",
        "category": "lifecycle",
        "severity": "success",
        "total": -1,
    }
    with pytest.raises(ValueError, match="invalid total"):
        _validate_parsed_dict(payload)


def test_event_emitter_skips_presentation_when_sink_is_none() -> None:
    emitter = EventEmitter(presentation_sink=None, technical_sink=lambda _event: None)
    emitter.emit(_sample_event())


def test_event_emitter_skips_technical_when_sink_is_none() -> None:
    seen: list[str] = []

    def presentation(event) -> None:
        seen.append(event.event_id.value)

    emitter = EventEmitter(presentation_sink=presentation, technical_sink=None)
    emitter.emit(_sample_event())
    assert seen == ["push.plan_verified"]


def test_recovery_confirmation_mismatch_emits_terminal_event(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from spell_sync.application.events import EventEmitter
    from spell_sync.application.reports import RecoveryOutcome
    from spell_sync.application.requests import ProjectRef, RecoveryRequest
    from spell_sync.application.services.context import ApplicationContext
    from spell_sync.application.services.recovery import RecoveryService
    from tests.tui.fake_service import sample_recovery_preview

    captured: list[TechnicalEvent] = []
    monkeypatch.setattr(
        "spell_sync.application.services.recovery.make_operation_emitter",
        lambda _sink: EventEmitter(presentation_sink=None, technical_sink=captured.append),
    )
    service = RecoveryService(
        ApplicationContext(
            runtime=MagicMock(),
            history_store=MagicMock(),
            state_paths=MagicMock(),
        )
    )
    preview = sample_recovery_preview()
    result = service.execute_recovery(
        RecoveryRequest(project=ProjectRef()),
        preview,
        confirmed_transaction_id="wrong-id",
    )
    assert result.outcome == RecoveryOutcome.FAILED
    assert len(captured) == 1
    terminal = captured[0]
    assert terminal.event_id is EventId.RECOVERY_FAILED
    assert terminal.reason is EventReason.CONFIRMATION_MISMATCH
    assert terminal.outcome is TerminalOutcome.FAILED
    assert terminal.phase is EventPhase.COMPLETED


def test_recovery_discard_success_emits_terminal_event(monkeypatch) -> None:
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from spell_sync.application.events import EventEmitter
    from spell_sync.application.reports import RecoveryOutcome, RecoveryStatus
    from spell_sync.application.requests import ProjectRef, RecoveryRequest
    from spell_sync.application.services.context import ApplicationContext
    from spell_sync.application.services.recovery import RecoveryService
    from tests.tui.fake_service import sample_recovery_preview

    captured: list[TechnicalEvent] = []
    monkeypatch.setattr(
        "spell_sync.application.services.recovery.make_operation_emitter",
        lambda _sink: EventEmitter(presentation_sink=None, technical_sink=captured.append),
    )
    scope = MagicMock()
    scope.context.wordlist_file = Path("/tmp/wordlist.txt")
    runtime = MagicMock()
    runtime.mutation_scope.return_value.__enter__.return_value = scope
    runtime.mutation_scope.return_value.__exit__.return_value = False
    service = RecoveryService(
        ApplicationContext(
            runtime=runtime,
            history_store=MagicMock(),
            state_paths=MagicMock(),
        )
    )
    preview = sample_recovery_preview(
        status=RecoveryStatus.CORRUPT_JOURNAL,
        can_discard=True,
        can_recover=False,
    )
    with patch(
        "spell_sync.application._operation_deps.safe_discard_journal_file",
        return_value=(True, None),
    ):
        result = service.execute_recovery_discard(
            RecoveryRequest(project=ProjectRef()),
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
        )
    assert result.outcome == RecoveryOutcome.DISCARDED
    assert len(captured) == 1
    terminal = captured[0]
    assert terminal.event_id is EventId.RECOVERY_DISCARDED
    assert terminal.outcome is TerminalOutcome.DISCARDED
    assert terminal.phase is EventPhase.COMPLETED
