"""Atomic project setup execution with rollback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..io import atomic_write
from ..operation_lock import OperationLocked, acquire_operation_lock
from ..push_journal import file_content_hash
from ..settings import ConfigStatus, load_config_result
from .prepare import PreparedProjectSetup, SetupFileAction

if TYPE_CHECKING:
    from ..diagnostics.event_metadata import EventReason
    from ..diagnostics.technical_event_model import (
        EventCategory,
        EventId,
        EventPhase,
        EventSeverity,
        TechnicalEvent,
    )

EventSink = Callable[["TechnicalEvent"], None]


class ProjectSetupOutcome(str, Enum):
    COMPLETED = "completed"
    STOPPED_SAFELY = "stopped_safely"
    SETUP_INCOMPLETE = "setup_incomplete"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectSetupExecution:
    prepared: PreparedProjectSetup
    outcome: ProjectSetupOutcome
    message: str
    created_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _fingerprint_matches(path: Path, fingerprint: str | None) -> bool:
    if fingerprint is None:
        return not path.is_file()
    current = file_content_hash(path)
    return current == fingerprint


def _emit_setup_event(
    event_sink: EventSink | None,
    *,
    setup_id: str,
    event_id: "EventId",
    severity: "EventSeverity | None" = None,
    phase: "EventPhase | None" = None,
    category: "EventCategory | None" = None,
    reason: "EventReason | None" = None,
    terminal: bool = False,
    outcome: ProjectSetupOutcome | None = None,
) -> None:
    from ..diagnostics.technical_event_builder import (
        build_technical_event,
        setup_outcome_to_terminal,
    )
    from ..diagnostics.technical_event_model import (
        EventCategory,
        EventPhase,
        EventSeverity,
        OperationKind,
    )

    if event_sink is None:
        return
    terminal_phase = EventPhase.COMPLETED if terminal else phase
    terminal_outcome = (
        setup_outcome_to_terminal(outcome) if terminal and outcome is not None else None
    )
    event_sink(
        build_technical_event(
            event_id=event_id,
            operation=OperationKind.SETUP,
            category=category or EventCategory.LIFECYCLE,
            severity=severity or EventSeverity.INFO,
            phase=terminal_phase,
            correlation_id=setup_id,
            reason=reason,
            outcome=terminal_outcome,
        )
    )


def _return_with_terminal(
    event_sink: EventSink | None,
    *,
    setup_id: str,
    execution: ProjectSetupExecution,
    event_id: "EventId",
    reason: "EventReason",
    severity: "EventSeverity | None" = None,
) -> ProjectSetupExecution:
    from ..diagnostics.technical_event_model import EventSeverity

    _emit_setup_event(
        event_sink,
        setup_id=setup_id,
        event_id=event_id,
        severity=severity or EventSeverity.ERROR,
        reason=reason,
        terminal=True,
        outcome=execution.outcome,
    )
    return execution


def execute_project_setup(
    prepared: PreparedProjectSetup,
    *,
    confirmed_setup_id: str,
    event_sink: EventSink | None = None,
) -> ProjectSetupExecution:
    from ..diagnostics.event_metadata import EventReason
    from ..diagnostics.technical_event_model import (
        EventCategory,
        EventId,
        EventPhase,
        EventSeverity,
    )

    setup_id = prepared.setup_id

    def emit(
        event_id: EventId,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        phase: EventPhase | None = None,
        category: EventCategory = EventCategory.LIFECYCLE,
    ) -> None:
        _emit_setup_event(
            event_sink,
            setup_id=setup_id,
            event_id=event_id,
            severity=severity,
            phase=phase,
            category=category,
        )

    if confirmed_setup_id != prepared.setup_id:
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.FAILED,
                message="Setup confirmation does not match the current preview.",
            ),
            event_id=EventId.SETUP_FAILED,
            reason=EventReason.CONFIRMATION_MISMATCH,
        )
    if not prepared.can_execute:
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                message="Setup preview has conflicts and cannot execute.",
            ),
            event_id=EventId.SETUP_STOPPED_SAFELY,
            reason=EventReason.PREVIEW_NOT_EXECUTABLE,
            severity=EventSeverity.WARNING,
        )

    emit(EventId.SETUP_VALIDATING, phase=EventPhase.PREPARING)
    for item in prepared.files:
        if item.action is SetupFileAction.CONFLICT:
            return _return_with_terminal(
                event_sink,
                setup_id=setup_id,
                execution=ProjectSetupExecution(
                    prepared=prepared,
                    outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                    message=f"Conflict detected: {item.relative_name}",
                ),
                event_id=EventId.SETUP_STOPPED_SAFELY,
                reason=EventReason.CONFLICT_DETECTED,
                severity=EventSeverity.WARNING,
            )
        if item.action is SetupFileAction.KEEP and item.fingerprint is not None:
            if not _fingerprint_matches(item.path, item.fingerprint):
                return _return_with_terminal(
                    event_sink,
                    setup_id=setup_id,
                    execution=ProjectSetupExecution(
                        prepared=prepared,
                        outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                        message=f"{item.relative_name} changed after preview.",
                    ),
                    event_id=EventId.SETUP_STOPPED_SAFELY,
                    reason=EventReason.FILE_CHANGED_AFTER_PREVIEW,
                    severity=EventSeverity.WARNING,
                )
        if item.action is SetupFileAction.CREATE and item.path.exists():
            return _return_with_terminal(
                event_sink,
                setup_id=setup_id,
                execution=ProjectSetupExecution(
                    prepared=prepared,
                    outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                    message=f"{item.relative_name} appeared after preview.",
                ),
                event_id=EventId.SETUP_STOPPED_SAFELY,
                reason=EventReason.FILE_APPEARED_AFTER_PREVIEW,
                severity=EventSeverity.WARNING,
            )

    created: list[Path] = []
    try:
        emit(EventId.SETUP_LOCK_ACQUIRED, phase=EventPhase.EXECUTING)
        with acquire_operation_lock(prepared.wordlist_path, "setup"):
            emit(EventId.SETUP_CONFLICTS_CHECKED, phase=EventPhase.EXECUTING)
            for directory in prepared.directories_to_create:
                emit(
                    EventId.SETUP_DIRECTORY_CREATED,
                    phase=EventPhase.EXECUTING,
                    category=EventCategory.TRANSACTION,
                )
                if not directory.is_dir():
                    directory.mkdir(parents=True, exist_ok=False)

            for item in prepared.files:
                if item.action is not SetupFileAction.CREATE:
                    continue
                if item.path.name.endswith(".toml"):
                    emit(
                        EventId.SETUP_CONFIG_CREATED,
                        phase=EventPhase.EXECUTING,
                        category=EventCategory.TRANSACTION,
                    )
                elif "whitelist" in item.relative_name:
                    emit(
                        EventId.SETUP_WHITELIST_CREATED,
                        phase=EventPhase.EXECUTING,
                        category=EventCategory.TRANSACTION,
                    )
                else:
                    emit(
                        EventId.SETUP_WORDLIST_CREATED,
                        phase=EventPhase.EXECUTING,
                        category=EventCategory.TRANSACTION,
                    )
                assert item.content is not None
                atomic_write(item.path, item.content, keep_backup=False)
                created.append(item.path)

            emit(EventId.SETUP_VERIFYING, phase=EventPhase.FINALIZING)
            config_result = load_config_result(wordlist=prepared.wordlist_path)
            if config_result.status not in (ConfigStatus.VALID, ConfigStatus.UNKNOWN_KEY):
                raise RuntimeError("Created configuration failed validation.")
    except OperationLocked:
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.FAILED,
                message="Another spell-sync process holds the project lock.",
            ),
            event_id=EventId.SETUP_FAILED,
            reason=EventReason.LOCK_UNAVAILABLE,
        )
    except FileExistsError as exc:
        _rollback_created(created)
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                message=str(exc),
            ),
            event_id=EventId.SETUP_STOPPED_SAFELY,
            reason=EventReason.FILE_EXISTS,
            severity=EventSeverity.WARNING,
        )
    except OSError as exc:
        incomplete = _rollback_created(created)
        outcome = ProjectSetupOutcome.SETUP_INCOMPLETE if incomplete else ProjectSetupOutcome.FAILED
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=outcome,
                message=str(exc),
                created_files=tuple(path.name for path in created),
            ),
            event_id=EventId.SETUP_INCOMPLETE if incomplete else EventId.SETUP_FAILED,
            reason=EventReason.IO_ERROR,
        )
    except RuntimeError as exc:
        incomplete = _rollback_created(created)
        outcome = ProjectSetupOutcome.SETUP_INCOMPLETE if incomplete else ProjectSetupOutcome.FAILED
        return _return_with_terminal(
            event_sink,
            setup_id=setup_id,
            execution=ProjectSetupExecution(
                prepared=prepared,
                outcome=outcome,
                message=str(exc),
                created_files=tuple(path.name for path in created),
            ),
            event_id=EventId.SETUP_INCOMPLETE if incomplete else EventId.SETUP_FAILED,
            reason=EventReason.CONFIG_VALIDATION_FAILED,
        )

    _emit_setup_event(
        event_sink,
        setup_id=setup_id,
        event_id=EventId.SETUP_COMPLETED,
        severity=EventSeverity.SUCCESS,
        phase=EventPhase.COMPLETED,
        category=EventCategory.LIFECYCLE,
        terminal=True,
        outcome=ProjectSetupOutcome.COMPLETED,
    )
    message = (
        "Project created. The existing canonical wordlist was kept unchanged."
        if prepared.existing_wordlist_kept
        else "Project created."
    )
    return ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message=message,
        created_files=tuple(path.name for path in created),
        warnings=prepared.warnings,
    )


def _rollback_created(paths: list[Path]) -> bool:
    leftover = False
    for path in reversed(paths):
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
        except OSError:
            leftover = True
    return leftover
