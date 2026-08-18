"""Presentation mapping for typed technical events."""

from ..guest_messages import RECOVERY_DISCARDED_TITLE
from .event_metadata import EventReason
from .events import (
    EventId,
    PresentedEvent,
    TechnicalEvent,
)

_RUNTIME_CHANGED_MESSAGE = "Project configuration or apps changed after the preview was created"

_MESSAGES: dict[EventId, str] = {
    EventId.PULL_VALIDATING: "Validating Collect my words preview",
    EventId.PULL_BLOCKED: "Collect my words blocked by lock, config, or recovery state",
    EventId.PULL_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.PULL_RUNTIME_CHANGED: _RUNTIME_CHANGED_MESSAGE,
    EventId.PULL_WORDLIST_MISMATCH: "Preview word list path mismatch",
    EventId.PULL_PLAN_VERIFIED: "Verifying prepared Collect my words plan",
    EventId.PULL_SOURCE_STARTED: "Merging dictionary source",
    EventId.PULL_WRITE_STARTED: "Writing personal word list",
    EventId.PULL_WORDLIST_CHANGED: "Word list changed after preview",
    EventId.PULL_WRITE_FAILED: "Collect my words write failed",
    EventId.PULL_COMPLETED: "Collect my words completed",
    EventId.PUSH_VALIDATING: "Validating configuration",
    EventId.PUSH_BLOCKED: "Update my apps blocked by lock, config, or recovery state",
    EventId.PUSH_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.PUSH_RUNTIME_CHANGED: _RUNTIME_CHANGED_MESSAGE,
    EventId.PUSH_TARGET_CHANGED: "An application changed after preview",
    EventId.PUSH_BUILDING_PLAN: "Building Update my apps plan",
    EventId.PUSH_PLAN_FAILED: "Update my apps plan failed",
    EventId.PUSH_PLAN_VERIFIED: "Prepared plan verified",
    EventId.PUSH_SNAPSHOTS_STARTED: "Creating recovery snapshots",
    EventId.PUSH_DRY_RUN_STARTED: "Starting Update my apps",
    EventId.PUSH_EXECUTION_STARTED: "Starting Update my apps",
    EventId.PUSH_WORDLIST_WRITE_STARTED: "Updating personal word list",
    EventId.PUSH_TARGET_STARTED: "Updating app dictionary",
    EventId.PUSH_ROLLBACK_STARTED: "Rolling back Update my apps",
    EventId.PUSH_FINALIZING: "Finishing Update my apps",
    EventId.PUSH_FAILED: "Update my apps aborted",
    EventId.PUSH_STOPPED_SAFELY: "Update my apps stopped after rollback",
    EventId.PUSH_RECOVERY_REQUIRED: "Update my apps stopped — recovery required",
    EventId.PUSH_COMPLETED: "Update my apps completed",
    EventId.RECOVERY_VALIDATING: "Checking interrupted-update record",
    EventId.RECOVERY_BLOCKED: "Recovery blocked by lock or configuration",
    EventId.RECOVERY_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.RECOVERY_SNAPSHOTS_VALIDATED: "Validating recovery snapshots",
    EventId.RECOVERY_CONFLICTS_CHECKED: "Checking recovery conflicts",
    EventId.RECOVERY_WORDLIST_RESTORE_STARTED: "Recovering word list",
    EventId.RECOVERY_TARGET_RESTORE_STARTED: "Recovering app dictionary",
    EventId.RECOVERY_TARGET_REMOVE_STARTED: "Removing created app dictionary",
    EventId.RECOVERY_FAILED: "Recovery incomplete",
    EventId.RECOVERY_CLEANUP_STARTED: "Cleaning recovery artifacts",
    EventId.RECOVERY_CLEANUP_COMPLETED: "Cleanup completed",
    EventId.RECOVERY_DISCARDED: RECOVERY_DISCARDED_TITLE,
    EventId.RECOVERY_COMPLETED: "Recovery completed",
    EventId.SETUP_VALIDATING: "Validating setup paths",
    EventId.SETUP_LOCK_ACQUIRED: "Acquiring project lock",
    EventId.SETUP_CONFLICTS_CHECKED: "Checking setup conflicts",
    EventId.SETUP_DIRECTORY_CREATED: "Creating project directory",
    EventId.SETUP_CONFIG_CREATED: "Writing configuration",
    EventId.SETUP_WHITELIST_CREATED: "Writing lint whitelist",
    EventId.SETUP_WORDLIST_CREATED: "Writing word list",
    EventId.SETUP_VERIFYING: "Verifying project files",
    EventId.SETUP_COMPLETED: "Project setup completed",
    EventId.SETUP_STOPPED_SAFELY: "Setup stopped safely",
    EventId.SETUP_FAILED: "Setup failed",
    EventId.SETUP_INCOMPLETE: "Setup incomplete",
    EventId.TARGETS_LOCK_ACQUIRED: "Acquiring project lock",
    EventId.TARGETS_CONFLICTS_CHECKED: "Checking configuration fingerprint",
    EventId.TARGETS_WRITE_STARTED: "Writing spell-sync.toml",
    EventId.TARGETS_VERIFYING: "Verifying configuration",
    EventId.TARGETS_COMPLETED: "Configuration updated",
    EventId.TARGETS_STOPPED_SAFELY: "Configuration update stopped safely",
    EventId.TARGETS_FAILED: "Configuration update failed",
    EventId.OPERATION_STARTED: "Operation started",
    EventId.OPERATION_COMPLETED: "Operation completed",
    EventId.OPERATION_FAILED: "Operation failed",
    EventId.OPERATION_ABORTED: "Operation aborted",
    EventId.DIAGNOSTICS_HISTORY_WRITE_FAILED: "Operation history could not be saved",
    EventId.DIAGNOSTICS_LOGGING_SETUP_FAILED: "Technical log unavailable",
    EventId.DIAGNOSTICS_DOCTOR_UNEXPECTED_FAILURE: "Doctor report could not be loaded",
    EventId.DIAGNOSTICS_TUI_LAUNCH_UNEXPECTED_FAILURE: "TUI failed to start",
    EventId.DIAGNOSTICS_PRESENTATION_SINK_FAILED: "Presentation sink failed",
    EventId.DIAGNOSTICS_TECHNICAL_SINK_FAILED: "Technical event sink failed",
}

_REASON_MESSAGES: dict[EventReason, str] = {
    EventReason.ROLLBACK_INCOMPLETE: "Push rollback did not complete cleanly",
    EventReason.JOURNAL_INVALID: "An interrupted update is still in progress",
}


def present_event(event: TechnicalEvent) -> PresentedEvent:
    message = _MESSAGES.get(event.event_id, event.event_id.value)
    if event.event_id is EventId.PUSH_TARGET_CHANGED and event.target_id:
        message = f"{event.target_id.value} changed after preview"
    elif event.event_id is EventId.PUSH_TARGET_STARTED and event.target_id:
        message = f"Updating {event.target_id.value}"
    elif event.event_id is EventId.PULL_SOURCE_STARTED and event.target_id:
        message = f"Merging {event.target_id.value}"
    elif event.event_id is EventId.RECOVERY_TARGET_RESTORE_STARTED and event.target_id:
        message = f"Recovering {event.target_id.value}"
    elif event.event_id is EventId.RECOVERY_TARGET_REMOVE_STARTED and event.target_id:
        message = f"Recovering {event.target_id.value}"
    elif event.event_id is EventId.RECOVERY_WORDLIST_RESTORE_STARTED:
        message = "Recovering word list"
    elif event.reason is not None and event.reason in _REASON_MESSAGES:
        message = _REASON_MESSAGES[event.reason]
    return PresentedEvent(
        operation=event.operation,
        event_id=event.event_id,
        message=message,
        severity=event.severity,
        stage=event.stage,
        target_id=event.target_id,
        completed=event.completed,
        total=event.total,
    )
