"""Post-setup dictionary target settings load, preview, and execute."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..application.event_metadata import EventReason
    from ..application.events import (
        EventCategory,
        EventId,
        EventPhase,
        EventSeverity,
        TechnicalEvent,
    )

from ..io import atomic_write
from ..operation_lock import OperationLocked, acquire_operation_lock
from ..push_journal import file_content_hash
from ..settings import ConfigStatus, config_blocks_mutating, load_config_result
from .discovery import (
    _CONFIG_TARGET_IDS,
    SetupTarget,
    discover_setup_targets,
    enabled_dictionary_targets,
    target_display_name,
)
from .draft import ProjectConfigDraft, SafetyConfig
from .render import render_project_config

_STALE_CONFIG_MESSAGE = (
    "Configuration update stopped safely\n"
    "spell-sync.toml changed after the preview was created.\n"
    "The newer file was not overwritten."
)


@dataclass(frozen=True)
class TargetSettingsSnapshot:
    config_path: Path
    wordlist_path: Path
    targets: tuple[SetupTarget, ...]
    enabled_target_ids: frozenset[str]
    load_error: str | None = None


@dataclass(frozen=True)
class PreparedTargetSettingsUpdate:
    update_id: str
    config_path: Path
    wordlist_path: Path
    selected_target_ids: frozenset[str]
    previous_target_ids: frozenset[str]
    enabled_target_ids: frozenset[str]
    disabled_target_ids: frozenset[str]
    rendered_config_bytes: bytes
    config_fingerprint_before: str | None
    warnings: tuple[str, ...]
    can_execute: bool


class TargetSettingsOutcome(str, Enum):
    COMPLETED = "completed"
    STOPPED_SAFELY = "stopped_safely"
    FAILED = "failed"


@dataclass(frozen=True)
class TargetSettingsExecution:
    prepared: PreparedTargetSettingsUpdate
    outcome: TargetSettingsOutcome
    message: str
    warnings: tuple[str, ...] = ()


EventSink = Callable[["TechnicalEvent"], None]


def _emit_targets_event(
    event_sink: EventSink | None,
    *,
    update_id: str,
    event_id: "EventId",
    severity: "EventSeverity | None" = None,
    phase: "EventPhase | None" = None,
    category: "EventCategory | None" = None,
    reason: "EventReason | None" = None,
    terminal: bool = False,
    outcome: TargetSettingsOutcome | None = None,
) -> None:
    from ..application.event_helpers import (
        build_technical_event,
        target_settings_outcome_to_terminal,
    )
    from ..application.events import EventCategory, EventPhase, EventSeverity, OperationKind

    if event_sink is None:
        return
    event_sink(
        build_technical_event(
            event_id=event_id,
            operation=OperationKind.TARGETS,
            category=category or EventCategory.LIFECYCLE,
            severity=severity or EventSeverity.INFO,
            phase=EventPhase.COMPLETED if terminal else phase,
            correlation_id=update_id,
            reason=reason,
            outcome=target_settings_outcome_to_terminal(outcome) if terminal and outcome else None,
        )
    )


def _return_with_terminal(
    event_sink: EventSink | None,
    *,
    update_id: str,
    execution: TargetSettingsExecution,
    event_id: "EventId",
    reason: "EventReason",
    severity: "EventSeverity | None" = None,
) -> TargetSettingsExecution:
    from ..application.events import EventSeverity

    _emit_targets_event(
        event_sink,
        update_id=update_id,
        event_id=event_id,
        severity=severity or EventSeverity.ERROR,
        reason=reason,
        terminal=True,
        outcome=execution.outcome,
    )
    return execution


def _project_config_path(wordlist: Path) -> Path:
    return wordlist.resolve().parent / "spell-sync.toml"


def _safety_from_config(config: dict[str, dict[str, Any]]) -> SafetyConfig:
    backup_keep = config.get("io", {}).get("backup_keep")
    if isinstance(backup_keep, int):
        return SafetyConfig(backup_keep=backup_keep)
    return SafetyConfig()


def resolve_enabled_targets(
    discovery_targets: tuple[SetupTarget, ...],
    *,
    selected_target_ids: frozenset[str],
    previous_target_ids: frozenset[str],
) -> frozenset[str]:
    enabled: set[str] = set()
    for target in discovery_targets:
        if target.identifier not in _CONFIG_TARGET_IDS:
            continue
        if not target.selectable:
            if target.identifier in previous_target_ids:
                enabled.add(target.identifier)
            continue
        if target.identifier in selected_target_ids:
            enabled.add(target.identifier)
    return frozenset(enabled)


def _update_id(
    *,
    config_fingerprint: str | None,
    rendered_config_bytes: bytes,
    enabled_target_ids: frozenset[str],
    selected_target_ids: frozenset[str],
) -> str:
    digest = hashlib.sha256()
    digest.update((config_fingerprint or "").encode("utf-8"))
    digest.update(rendered_config_bytes)
    for target_id in sorted(enabled_target_ids):
        digest.update(target_id.encode("utf-8"))
    for target_id in sorted(selected_target_ids):
        digest.update(target_id.encode("utf-8"))
    return digest.hexdigest()[:16]


def _fingerprint_matches(path: Path, fingerprint: str | None) -> bool:
    if fingerprint is None:
        return not path.is_file()
    return file_content_hash(path) == fingerprint


def _enabled_from_loaded_config(config: dict[str, dict[str, Any]] | None) -> frozenset[str]:
    if config is None:
        return frozenset()
    return enabled_dictionary_targets(config)


def load_target_settings_snapshot(*, wordlist: Path) -> TargetSettingsSnapshot:
    config_path = _project_config_path(wordlist)
    config_result = load_config_result(wordlist=wordlist)
    if config_result.status is ConfigStatus.ABSENT:
        return TargetSettingsSnapshot(
            config_path=config_path,
            wordlist_path=wordlist,
            targets=(),
            enabled_target_ids=frozenset(),
            load_error="spell-sync.toml is missing.",
        )
    if config_blocks_mutating(config_result):
        detail = (
            config_result.diagnostics[0].message
            if config_result.diagnostics
            else config_result.status.value
        )
        return TargetSettingsSnapshot(
            config_path=config_path,
            wordlist_path=wordlist,
            targets=(),
            enabled_target_ids=frozenset(),
            load_error=detail,
        )
    config = config_result.config or {}
    previous = _enabled_from_loaded_config(config)
    discovery = discover_setup_targets(
        selected_targets=tuple(sorted(previous)),
        enabled_targets=previous,
    )
    return TargetSettingsSnapshot(
        config_path=config_path,
        wordlist_path=wordlist,
        targets=discovery.targets,
        enabled_target_ids=previous,
    )


def prepare_target_settings_update(
    *,
    wordlist: Path,
    selected_target_ids: frozenset[str],
    pending_recovery: bool = False,
) -> PreparedTargetSettingsUpdate:
    config_path = _project_config_path(wordlist)
    config_result = load_config_result(wordlist=wordlist)
    warnings: list[str] = []
    can_execute = True

    if pending_recovery:
        warnings.append("Pending recovery blocks configuration updates.")
        can_execute = False

    if config_result.status is ConfigStatus.ABSENT:
        return PreparedTargetSettingsUpdate(
            update_id="unavailable",
            config_path=config_path,
            wordlist_path=wordlist,
            selected_target_ids=selected_target_ids,
            previous_target_ids=frozenset(),
            enabled_target_ids=frozenset(),
            disabled_target_ids=frozenset(),
            rendered_config_bytes=b"",
            config_fingerprint_before=None,
            warnings=tuple(warnings + ["spell-sync.toml is missing."]),
            can_execute=False,
        )

    if config_blocks_mutating(config_result):
        detail = (
            config_result.diagnostics[0].message
            if config_result.diagnostics
            else config_result.status.value
        )
        return PreparedTargetSettingsUpdate(
            update_id="unavailable",
            config_path=config_path,
            wordlist_path=wordlist,
            selected_target_ids=selected_target_ids,
            previous_target_ids=frozenset(),
            enabled_target_ids=frozenset(),
            disabled_target_ids=frozenset(),
            rendered_config_bytes=b"",
            config_fingerprint_before=file_content_hash(config_path)
            if config_path.is_file()
            else None,
            warnings=tuple(warnings + [detail]),
            can_execute=False,
        )

    config = config_result.config or {}
    previous = _enabled_from_loaded_config(config)
    discovery = discover_setup_targets(
        selected_targets=tuple(sorted(previous)),
        enabled_targets=previous,
    )
    known_ids = {target.identifier for target in discovery.targets}
    unknown = selected_target_ids - known_ids
    if unknown:
        warnings.append(
            "Unknown target identifiers ignored: " + ", ".join(sorted(unknown)),
        )

    enabled = resolve_enabled_targets(
        discovery.targets,
        selected_target_ids=selected_target_ids,
        previous_target_ids=previous,
    )
    enabled_delta = enabled - previous
    disabled_delta = previous - enabled

    draft = ProjectConfigDraft(
        schema_version=1,
        enabled_targets=tuple(sorted(enabled)),
        safety=_safety_from_config(config),
    )
    rendered = render_project_config(draft, existing_config=config)
    fingerprint = file_content_hash(config_path)
    update_id = _update_id(
        config_fingerprint=fingerprint,
        rendered_config_bytes=rendered,
        enabled_target_ids=enabled,
        selected_target_ids=selected_target_ids,
    )

    if enabled == previous:
        warnings.append("No configuration changes to apply.")
        can_execute = False

    return PreparedTargetSettingsUpdate(
        update_id=update_id,
        config_path=config_path,
        wordlist_path=wordlist,
        selected_target_ids=selected_target_ids,
        previous_target_ids=previous,
        enabled_target_ids=enabled_delta,
        disabled_target_ids=disabled_delta,
        rendered_config_bytes=rendered,
        config_fingerprint_before=fingerprint,
        warnings=tuple(warnings),
        can_execute=can_execute,
    )


def execute_target_settings_update(
    prepared: PreparedTargetSettingsUpdate,
    *,
    confirmed_update_id: str,
    event_sink: EventSink | None = None,
) -> TargetSettingsExecution:
    from ..application.event_metadata import EventReason
    from ..application.events import EventCategory, EventId, EventPhase, EventSeverity

    update_id = prepared.update_id

    def emit(
        event_id: EventId,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        phase: EventPhase | None = None,
        category: EventCategory = EventCategory.LIFECYCLE,
    ) -> None:
        _emit_targets_event(
            event_sink,
            update_id=update_id,
            event_id=event_id,
            severity=severity,
            phase=phase,
            category=category,
        )

    if confirmed_update_id != prepared.update_id:
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.FAILED,
                message="Configuration confirmation does not match the current preview.",
            ),
            event_id=EventId.TARGETS_FAILED,
            reason=EventReason.CONFIRMATION_MISMATCH,
        )
    if not prepared.can_execute:
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.STOPPED_SAFELY,
                message="Configuration preview cannot execute.",
                warnings=prepared.warnings,
            ),
            event_id=EventId.TARGETS_STOPPED_SAFELY,
            reason=EventReason.PREVIEW_NOT_EXECUTABLE,
            severity=EventSeverity.WARNING,
        )

    if not _fingerprint_matches(prepared.config_path, prepared.config_fingerprint_before):
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.STOPPED_SAFELY,
                message=_STALE_CONFIG_MESSAGE,
                warnings=prepared.warnings,
            ),
            event_id=EventId.TARGETS_STOPPED_SAFELY,
            reason=EventReason.STALE_CONFIG,
            severity=EventSeverity.WARNING,
        )

    try:
        emit(EventId.TARGETS_LOCK_ACQUIRED, phase=EventPhase.EXECUTING)
        with acquire_operation_lock(prepared.wordlist_path, "targets"):
            emit(EventId.TARGETS_CONFLICTS_CHECKED, phase=EventPhase.EXECUTING)
            if not _fingerprint_matches(prepared.config_path, prepared.config_fingerprint_before):
                return _return_with_terminal(
                    event_sink,
                    update_id=update_id,
                    execution=TargetSettingsExecution(
                        prepared=prepared,
                        outcome=TargetSettingsOutcome.STOPPED_SAFELY,
                        message=_STALE_CONFIG_MESSAGE,
                        warnings=prepared.warnings,
                    ),
                    event_id=EventId.TARGETS_STOPPED_SAFELY,
                    reason=EventReason.STALE_CONFIG,
                    severity=EventSeverity.WARNING,
                )
            emit(
                EventId.TARGETS_WRITE_STARTED,
                phase=EventPhase.EXECUTING,
                category=EventCategory.TRANSACTION,
            )
            atomic_write(prepared.config_path, prepared.rendered_config_bytes, keep_backup=True)
            emit(EventId.TARGETS_VERIFYING, phase=EventPhase.FINALIZING)
            config_result = load_config_result(wordlist=prepared.wordlist_path)
            if config_result.status in (
                ConfigStatus.SYNTAX_ERROR,
                ConfigStatus.INVALID_TYPE,
                ConfigStatus.UNSUPPORTED_SCHEMA,
            ):
                raise RuntimeError("Updated configuration failed validation.")
            loaded = _enabled_from_loaded_config(config_result.config)
            expected = prepared.previous_target_ids | prepared.enabled_target_ids
            expected = expected - prepared.disabled_target_ids
            if loaded != expected:
                raise RuntimeError("Updated configuration does not match the preview.")
    except OperationLocked:
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.FAILED,
                message="Another spell-sync process holds the project lock.",
                warnings=prepared.warnings,
            ),
            event_id=EventId.TARGETS_FAILED,
            reason=EventReason.LOCK_UNAVAILABLE,
        )
    except OSError as exc:
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.FAILED,
                message=str(exc),
                warnings=prepared.warnings,
            ),
            event_id=EventId.TARGETS_FAILED,
            reason=EventReason.WRITE_FAILED,
        )
    except RuntimeError as exc:
        return _return_with_terminal(
            event_sink,
            update_id=update_id,
            execution=TargetSettingsExecution(
                prepared=prepared,
                outcome=TargetSettingsOutcome.FAILED,
                message=str(exc),
                warnings=prepared.warnings,
            ),
            event_id=EventId.TARGETS_FAILED,
            reason=EventReason.VERIFICATION_MISMATCH,
        )

    _emit_targets_event(
        event_sink,
        update_id=update_id,
        event_id=EventId.TARGETS_COMPLETED,
        severity=EventSeverity.SUCCESS,
        phase=EventPhase.COMPLETED,
        terminal=True,
        outcome=TargetSettingsOutcome.COMPLETED,
    )
    enabled_names = ", ".join(
        target_display_name(target_id) for target_id in sorted(prepared.enabled_target_ids)
    )
    disabled_names = ", ".join(
        target_display_name(target_id) for target_id in sorted(prepared.disabled_target_ids)
    )
    parts: list[str] = []
    if enabled_names:
        parts.append(f"Enabled: {enabled_names}")
    if disabled_names:
        parts.append(f"Disabled: {disabled_names}")
    message = "; ".join(parts) if parts else "Configuration updated."
    return TargetSettingsExecution(
        prepared=prepared,
        outcome=TargetSettingsOutcome.COMPLETED,
        message=message,
        warnings=prepared.warnings,
    )
