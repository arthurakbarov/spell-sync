"""Stable string constants for push skipped reasons."""

from __future__ import annotations


class PushSkipReason:
    UNREADABLE = "unreadable"
    CORRUPT = "corrupt"
    BACKUP_FAILED = "backup_failed"
    BLOCKED_BY_USER = "blocked_by_user"
    RUNNING_APP = "running_app"


PUSH_SKIP_DETAILS: dict[str, str] = {
    PushSkipReason.UNREADABLE: "no access — push skipped",
    PushSkipReason.CORRUPT: "corrupt or unsupported — push skipped",
    PushSkipReason.BACKUP_FAILED: "backup failed — push skipped",
    PushSkipReason.BLOCKED_BY_USER: "blocked before push",
}
