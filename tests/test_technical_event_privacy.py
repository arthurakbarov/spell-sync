"""Privacy guards for technical events, history, and support reports."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from spell_sync.application.event_metadata import (
    CorrelationId,
    EventReason,
    TargetId,
    TerminalOutcome,
)
from spell_sync.application.events import (
    EventCategory,
    EventId,
    EventSeverity,
    EventStage,
    OperationKind,
    TechnicalEvent,
)
from spell_sync.application.requests import (
    PrepareTargetSettingsUpdateRequest,
    ProjectRef,
    SupportReportRequest,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.application.support_report import format_support_report_text, support_report_to_dict
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.technical_event_log import (
    serialize_technical_event,
    write_technical_event,
)
from spell_sync.diagnostics.technical_logging import reset_logging_for_tests
from spell_sync.project_setup.discovery import SetupTarget, SetupTargetDiscovery
from spell_sync.project_setup.target_settings import TargetSettingsOutcome

SENSITIVE_WORD = "SENSITIVE_USER_WORD_7f3a"
SECRET_TOKEN = "secret-token-value"
PRIVATE_HOME = "/home/private-user"
PRIVATE_USERS = "/Users/private-user"


def _assert_sentinels_absent(text: str) -> None:
    for token in (
        SENSITIVE_WORD,
        SECRET_TOKEN,
        PRIVATE_HOME,
        PRIVATE_USERS,
        "raw-spell-sync-config",
        "line\nbreak",
        "target with spaces",
    ):
        assert token not in text, f"leaked sensitive token: {token!r}"


def _mock_discovery(enabled: frozenset[str]) -> SetupTargetDiscovery:
    targets = (
        SetupTarget(
            identifier="chrome",
            display_name="Chrome",
            path=Path(f"{PRIVATE_HOME}/chrome.txt"),
            format_name="text",
            detected=True,
            available=True,
            readable=True,
            supported=True,
            enabled_by_default=True,
            selectable=True,
            word_count=3,
            status="ok",
            detail=None,
            enabled="chrome" in enabled,
        ),
        SetupTarget(
            identifier="edge",
            display_name="Edge",
            path=Path(f"{PRIVATE_HOME}/edge.txt"),
            format_name="text",
            detected=True,
            available=True,
            readable=True,
            supported=True,
            enabled_by_default=True,
            selectable=True,
            word_count=3,
            status="ok",
            detail=None,
            enabled="edge" in enabled,
        ),
    )
    return SetupTargetDiscovery(
        targets=targets,
        default_enabled=tuple(sorted(enabled)),
    )


@pytest.fixture
def sensitive_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "home" / "private-user"
    project.mkdir(parents=True)
    wordlist = project / "wordlist.txt"
    wordlist.write_text(f"{SENSITIVE_WORD}\n{SECRET_TOKEN}\nalpha\n", encoding="utf-8")
    config = project / "spell-sync.toml"
    config.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
    return wordlist, config


@pytest.mark.parametrize(
    "factory",
    [
        lambda v: CorrelationId.parse(v),
        lambda v: TargetId.parse(v),
        lambda v: EventReason(v),
        lambda v: TerminalOutcome(v),
    ],
    ids=["correlation_id", "target_id", "reason", "outcome"],
)
@pytest.mark.parametrize(
    "value",
    [
        SENSITIVE_WORD,
        SECRET_TOKEN,
        PRIVATE_HOME,
        PRIVATE_USERS,
        "raw-spell-sync-config",
        "line\nbreak",
        "target with spaces",
    ],
)
def test_unsafe_metadata_values_rejected(factory, value: str) -> None:
    with pytest.raises(ValueError):
        factory(value)


def test_serializer_and_writer_omit_unsafe_correlation(tmp_path) -> None:
    reset_logging_for_tests()
    paths = resolve_app_state_paths(state_root=tmp_path / "state")
    event = TechnicalEvent(
        event_id=EventId.PUSH_COMPLETED,
        operation=OperationKind.PUSH,
        category=EventCategory.LIFECYCLE,
        severity=EventSeverity.SUCCESS,
        correlation_id=CorrelationId.parse("safe-plan-id"),
    )
    line = serialize_technical_event(event)
    _assert_sentinels_absent(line)
    from spell_sync.diagnostics.technical_logging import configure_file_logging

    configure_file_logging(paths)
    write_technical_event(event)
    log_text = paths.technical_log.read_text(encoding="utf-8")
    _assert_sentinels_absent(log_text)


def test_technical_events_do_not_leak_sentinels(
    tmp_path: Path,
    sensitive_project: tuple[Path, Path],
) -> None:
    reset_logging_for_tests()
    wordlist, _config = sensitive_project
    state = resolve_app_state_paths(state_root=tmp_path / "state")
    service = SpellSyncService(state_paths=state, enable_file_logging=True)

    with patch(
        "spell_sync.project_setup.target_settings.discover_setup_targets",
        side_effect=lambda *, enabled_targets=None: _mock_discovery(enabled_targets or frozenset()),
    ):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset({"edge"}),
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
        report = service.build_target_settings_report(execution)

    assert execution.outcome == TargetSettingsOutcome.COMPLETED
    assert report.operation == "targets"

    log_text = (
        state.technical_log.read_text(encoding="utf-8") if state.technical_log.is_file() else ""
    )
    history_text = (
        state.history_file.read_text(encoding="utf-8") if state.history_file.is_file() else ""
    )
    support = service.load_support_report(
        SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
    )
    support_json = json.dumps(support_report_to_dict(support), sort_keys=True)
    support_text = format_support_report_text(support)

    for blob in (log_text, history_text, support_json, support_text):
        _assert_sentinels_absent(blob)


def test_present_event_maps_target_and_reason_specific_messages() -> None:
    from spell_sync.application.event_presenter import present_event

    base = dict(
        operation=OperationKind.PUSH,
        category=EventCategory.LIFECYCLE,
        severity=EventSeverity.INFO,
        stage=EventStage.EXECUTING,
        correlation_id=CorrelationId.parse("corr-123"),
    )
    changed = present_event(
        TechnicalEvent(
            event_id=EventId.PUSH_TARGET_CHANGED,
            target_id=TargetId.parse("cursor"),
            **base,
        )
    )
    assert changed.message == "cursor changed after preview"

    started = present_event(
        TechnicalEvent(
            event_id=EventId.PUSH_TARGET_STARTED,
            target_id=TargetId.parse("chrome"),
            **base,
        )
    )
    assert started.message == "Updating chrome"

    restore = present_event(
        TechnicalEvent(
            event_id=EventId.RECOVERY_TARGET_RESTORE_STARTED,
            operation=OperationKind.RECOVER,
            category=EventCategory.RECOVERY,
            severity=EventSeverity.INFO,
            stage=EventStage.EXECUTING,
            correlation_id=CorrelationId.parse("corr-123"),
            target_id=TargetId.parse("vscode"),
        )
    )
    assert restore.message == "Recovering vscode"

    reason = present_event(
        TechnicalEvent(
            event_id=EventId.PUSH_FAILED,
            operation=OperationKind.PUSH,
            category=EventCategory.TRANSACTION,
            severity=EventSeverity.ERROR,
            stage=EventStage.EXECUTING,
            correlation_id=CorrelationId.parse("corr-123"),
            reason=EventReason.ROLLBACK_INCOMPLETE,
        )
    )
    assert reason.message == "Push rollback did not complete cleanly"
