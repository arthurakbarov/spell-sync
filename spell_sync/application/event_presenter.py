"""Presentation mapping for typed technical events."""

from __future__ import annotations

from .events import (
    EventId,
    PresentedEvent,
    TechnicalEvent,
)

_RUNTIME_CHANGED_MESSAGE = "Project configuration or targets changed after the preview was created"

_MESSAGES: dict[EventId, str] = {
    EventId.PULL_VALIDATING: "Validating pull preview",
    EventId.PULL_BLOCKED: "Pull blocked by lock, config, or recovery state",
    EventId.PULL_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.PULL_RUNTIME_CHANGED: _RUNTIME_CHANGED_MESSAGE,
    EventId.PULL_WORDLIST_MISMATCH: "Preview wordlist path mismatch",
    EventId.PULL_PLAN_VERIFIED: "Verifying prepared pull plan",
    EventId.PULL_WRITE_STARTED: "Writing canonical wordlist",
    EventId.PULL_WORDLIST_CHANGED: "Wordlist changed after preview",
    EventId.PULL_WRITE_FAILED: "Pull write failed",
    EventId.PULL_COMPLETED: "Pull completed",
    EventId.PUSH_VALIDATING: "Validating configuration",
    EventId.PUSH_BLOCKED: "Push blocked by lock, config, or recovery state",
    EventId.PUSH_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.PUSH_RUNTIME_CHANGED: _RUNTIME_CHANGED_MESSAGE,
    EventId.PUSH_TARGET_CHANGED: "Target changed after preview",
    EventId.PUSH_BUILDING_PLAN: "Building push plan",
    EventId.PUSH_PLAN_FAILED: "Push plan failed",
    EventId.PUSH_PLAN_VERIFIED: "Prepared plan verified",
    EventId.PUSH_SNAPSHOTS_STARTED: "Creating recovery snapshots",
    EventId.PUSH_DRY_RUN_STARTED: "Starting push execution",
    EventId.PUSH_EXECUTION_STARTED: "Starting push execution",
    EventId.PUSH_WORDLIST_WRITE_STARTED: "Updating canonical wordlist",
    EventId.PUSH_TARGET_STARTED: "Updating target dictionary",
    EventId.PUSH_ROLLBACK_STARTED: "Rolling back push transaction",
    EventId.PUSH_FINALIZING: "Finalizing transaction",
    EventId.PUSH_FAILED: "Push aborted",
    EventId.PUSH_STOPPED_SAFELY: "Push stopped after rollback handling",
    EventId.PUSH_RECOVERY_REQUIRED: "Push stopped; recovery required",
    EventId.PUSH_COMPLETED: "Push completed",
    EventId.RECOVERY_VALIDATING: "Validating journal",
    EventId.RECOVERY_BLOCKED: "Recovery blocked by lock or configuration",
    EventId.RECOVERY_LOCK_ACQUIRED: "Operation lock acquired",
    EventId.RECOVERY_SNAPSHOTS_VALIDATED: "Validating recovery snapshots",
    EventId.RECOVERY_CONFLICTS_CHECKED: "Checking recovery conflicts",
    EventId.RECOVERY_WORDLIST_RESTORE_STARTED: "Recovering wordlist",
    EventId.RECOVERY_TARGET_RESTORE_STARTED: "Recovering target",
    EventId.RECOVERY_TARGET_REMOVE_STARTED: "Removing created target",
    EventId.RECOVERY_FAILED: "Recovery incomplete",
    EventId.RECOVERY_CLEANUP_STARTED: "Cleaning recovery artifacts",
    EventId.RECOVERY_CLEANUP_COMPLETED: "Cleanup completed",
    EventId.RECOVERY_COMPLETED: "Recovery completed",
    EventId.SETUP_VALIDATING: "Validating setup paths",
    EventId.SETUP_LOCK_ACQUIRED: "Acquiring project lock",
    EventId.SETUP_CONFLICTS_CHECKED: "Checking setup conflicts",
    EventId.SETUP_DIRECTORY_CREATED: "Creating project directory",
    EventId.SETUP_CONFIG_CREATED: "Writing configuration",
    EventId.SETUP_WHITELIST_CREATED: "Writing lint whitelist",
    EventId.SETUP_WORDLIST_CREATED: "Writing wordlist",
    EventId.SETUP_VERIFYING: "Verifying project files",
    EventId.SETUP_COMPLETED: "Project setup completed",
    EventId.TARGETS_LOCK_ACQUIRED: "Acquiring project lock",
    EventId.TARGETS_CONFLICTS_CHECKED: "Checking configuration fingerprint",
    EventId.TARGETS_WRITE_STARTED: "Writing spell-sync.toml",
    EventId.TARGETS_VERIFYING: "Verifying configuration",
    EventId.TARGETS_COMPLETED: "Configuration updated",
    EventId.DIAGNOSTICS_HISTORY_WRITE_FAILED: "Operation history could not be saved",
    EventId.DIAGNOSTICS_LOGGING_SETUP_FAILED: "Technical log unavailable",
}

_REASON_MESSAGES: dict[str, str] = {
    "rollback_incomplete": "Push rollback did not complete cleanly",
    "journal_in_progress": "Push journal still in progress",
}


def present_event(event: TechnicalEvent) -> PresentedEvent:
    message = _MESSAGES.get(event.event_id, event.event_id.value)
    if event.event_id is EventId.PUSH_TARGET_CHANGED and event.target_id:
        message = f"{event.target_id} changed after preview"
    elif event.event_id is EventId.PUSH_TARGET_STARTED and event.target_id:
        message = f"Updating {event.target_id}"
    elif event.event_id is EventId.RECOVERY_TARGET_RESTORE_STARTED and event.target_id:
        message = f"Recovering {event.target_id}"
    elif event.event_id is EventId.RECOVERY_TARGET_REMOVE_STARTED and event.target_id:
        message = f"Recovering {event.target_id}"
    elif event.event_id is EventId.RECOVERY_WORDLIST_RESTORE_STARTED:
        message = "Recovering wordlist"
    elif event.reason_code and event.reason_code in _REASON_MESSAGES:
        message = _REASON_MESSAGES[event.reason_code]
    return PresentedEvent(
        operation=event.operation,
        event_id=event.event_id,
        message=message,
        severity=event.severity,
        phase=event.phase,
        target_id=event.target_id,
        completed=event.completed,
        total=event.total,
    )
