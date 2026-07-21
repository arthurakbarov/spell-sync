"""Validated safe metadata for structured technical events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TARGET_ID_PATTERN = re.compile(r"^(?:[a-z][a-z0-9_-]{0,63}|[a-z]+:[a-zA-Z0-9._ -]{1,64})$")
_PRIVACY_DENY_SUBSTRINGS = (
    "/home/",
    "/users/",
    "private-user",
    "secret",
    "token",
    "sensitive_user_word",
    "raw-spell-sync-config",
)


class EventReason(str, Enum):
    CONFIRMATION_MISMATCH = "confirmation_mismatch"
    PREVIEW_NOT_EXECUTABLE = "preview_not_executable"
    CONFLICT_DETECTED = "conflict_detected"
    FILE_CHANGED_AFTER_PREVIEW = "file_changed_after_preview"
    FILE_APPEARED_AFTER_PREVIEW = "file_appeared_after_preview"
    LOCK_UNAVAILABLE = "lock_unavailable"
    FILE_EXISTS = "file_exists"
    IO_ERROR = "io_error"
    CONFIG_VALIDATION_FAILED = "config_validation_failed"
    ROLLBACK_INCOMPLETE = "rollback_incomplete"
    STALE_CONFIG = "stale_config"
    VERIFICATION_MISMATCH = "verification_mismatch"
    RUNTIME_CHANGED = "runtime_changed"
    TARGET_CHANGED = "target_changed"
    WORDLIST_MISMATCH = "wordlist_mismatch"
    WORDLIST_CHANGED = "wordlist_changed"
    WRITE_FAILED = "write_failed"
    JOURNAL_INVALID = "journal_invalid"
    JOURNAL_CHANGED = "journal_changed"
    RECOVERY_UNAVAILABLE = "recovery_unavailable"
    CLEANUP_FAILED = "cleanup_failed"
    HISTORY_APPEND_FAILED = "history_append_failed"
    LOGGING_SETUP_FAILED = "logging_setup_failed"
    EXECUTION_BLOCKED = "execution_blocked"


class TerminalOutcome(str, Enum):
    COMPLETED = "completed"
    STOPPED_SAFELY = "stopped_safely"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    RECOVERY_REQUIRED = "recovery_required"
    CONFLICTED = "conflicted"
    RECOVERED = "recovered"
    RECOVERED_WITH_WARNINGS = "recovered_with_warnings"
    CLEANUP_COMPLETED = "cleanup_completed"
    DISCARDED = "discarded"


def _validate_correlation(value: str) -> None:
    if not _CORRELATION_PATTERN.fullmatch(value):
        raise ValueError("invalid correlation id")
    lowered = value.lower()
    if any(token in lowered for token in _PRIVACY_DENY_SUBSTRINGS):
        raise ValueError("invalid correlation id")


def _validate_target_id(value: str) -> None:
    if not _TARGET_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid target id")
    lowered = value.lower()
    if any(token in lowered for token in _PRIVACY_DENY_SUBSTRINGS):
        raise ValueError("invalid target id")


@dataclass(frozen=True, slots=True)
class CorrelationId:
    value: str

    def __post_init__(self) -> None:
        _validate_correlation(self.value)

    @classmethod
    def parse(cls, value: str) -> CorrelationId:
        return cls(value)


@dataclass(frozen=True, slots=True)
class TargetId:
    value: str

    def __post_init__(self) -> None:
        _validate_target_id(self.value)

    @classmethod
    def parse(cls, value: str) -> TargetId:
        return cls(value)
