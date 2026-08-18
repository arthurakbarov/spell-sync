"""UI-neutral user notices with a single text catalog."""

from dataclasses import dataclass
from enum import StrEnum

from ..project_setup.discovery import dictionary_family_id
from ..skip_reasons import PushSkipReason
from .reports import DashboardIssue, DashboardSeverity


class NoticeSeverity(StrEnum):
    BLOCKED = "blocked"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class NoticeTemplate:
    title: str
    explanation: str
    suggested_action: str


@dataclass(frozen=True)
class UserNotice:
    code: str
    severity: NoticeSeverity
    title: str
    explanation: str
    suggested_action: str | None
    technical_detail: str | None = None


NOTICE_CATALOG: dict[str, NoticeTemplate] = {
    "invalid_config": NoticeTemplate(
        title="Invalid configuration",
        explanation="spell-sync.toml failed validation and blocks write operations.",
        suggested_action="Fix spell-sync.toml, then run spell-sync config-check.",
    ),
    "unreadable_wordlist": NoticeTemplate(
        title="Word list unreadable",
        explanation="Your personal word list cannot be read.",
        suggested_action="Check file permissions and path, then run spell-sync doctor.",
    ),
    "pending_recovery": NoticeTemplate(
        title="Pending recovery",
        explanation="An interrupted update requires recovery before writes.",
        suggested_action="Open Finish interrupted update and complete the pending restore.",
    ),
    "cleanup_pending": NoticeTemplate(
        title="Recovery files remain",
        explanation="The update finished, but recovery files remain.",
        suggested_action="Open Clean up leftover files and remove the leftover records.",
    ),
    "corrupt_journal": NoticeTemplate(
        title="Damaged interrupted-update record",
        explanation="The interrupted-update record is damaged or uses an unsupported format.",
        suggested_action="Open Finish interrupted update, or ask for help with a support report.",
    ),
    "operation_locked": NoticeTemplate(
        title="Operation lock active",
        explanation="Another spell-sync process is running in this project.",
        suggested_action="Wait for the other process to finish.",
    ),
    "target_corrupt": NoticeTemplate(
        title="App dictionary damaged",
        explanation="An app custom dictionary is corrupt or unsupported.",
        suggested_action="Repair the dictionary file, or turn the app off in Applications.",
    ),
    "target_unreadable": NoticeTemplate(
        title="App dictionary unreadable",
        explanation="An app custom dictionary could not be read.",
        suggested_action="Check permissions, or turn the app off in Applications.",
    ),
    "application_running": NoticeTemplate(
        title="Application was running",
        explanation="The app was running, so its dictionary was not updated.",
        suggested_action="Close the application and run Update my apps again.",
    ),
    "backup_failed": NoticeTemplate(
        title="Dictionary backup failed",
        explanation="The app dictionary could not be backed up, so it was not updated.",
        suggested_action="Check disk space and permissions, then run Update my apps again.",
    ),
    "update_blocked": NoticeTemplate(
        title="App was skipped",
        explanation="This app was skipped before Update my apps wrote dictionaries.",
        suggested_action="Turn the app on in Applications, then run Update my apps again.",
    ),
    "target_skipped": NoticeTemplate(
        title="App dictionary skipped",
        explanation="This app dictionary was not written during Update my apps.",
        suggested_action="Check Health, then run Update my apps again.",
    ),
    "stale_preview": NoticeTemplate(
        title="Preview is stale",
        explanation="An app dictionary changed after the preview was created.",
        suggested_action="Rebuild the preview and confirm again.",
    ),
    "external_change": NoticeTemplate(
        title="External change detected",
        explanation="A file changed outside Spell Sync during the operation.",
        suggested_action="Review the app state, then rebuild the preview.",
    ),
    "removal_confirmation_required": NoticeTemplate(
        title="Removal confirmation required",
        explanation="Update my apps would remove more words than the configured limit allows.",
        suggested_action="Review removals, then confirm or adjust spell-sync.toml limits.",
    ),
    "rollback_incomplete": NoticeTemplate(
        title="Rollback incomplete",
        explanation="Automatic rollback did not finish cleanly.",
        suggested_action="Open Finish interrupted update before another write operation.",
    ),
    "history_write_failed": NoticeTemplate(
        title="History write failed",
        explanation="The operation finished, but its history record could not be saved.",
        suggested_action="Check History permissions. The operation result still stands.",
    ),
}

_DASHBOARD_CODE_ALIASES: dict[str, str] = {
    "operation_lock": "operation_locked",
    "skipped_unreadable": "target_unreadable",
    "corrupt_target": "target_corrupt",
}

_DASHBOARD_SEVERITY: dict[DashboardSeverity, NoticeSeverity] = {
    DashboardSeverity.BLOCKED: NoticeSeverity.BLOCKED,
    DashboardSeverity.WARNING: NoticeSeverity.WARNING,
    DashboardSeverity.READY: NoticeSeverity.INFO,
}


def catalog_entry(code: str) -> NoticeTemplate:
    try:
        return NOTICE_CATALOG[code]
    except KeyError as exc:
        raise KeyError(f"unknown notice code: {code}") from exc


def build_notice(
    code: str,
    *,
    severity: NoticeSeverity = NoticeSeverity.WARNING,
    target_id: str | None = None,
    detail: str | None = None,
    explanation: str | None = None,
) -> UserNotice:
    template = catalog_entry(code)
    technical = _technical_detail(code, target_id=target_id, detail=detail)
    return UserNotice(
        code=code,
        severity=severity,
        title=template.title,
        explanation=explanation or template.explanation,
        suggested_action=template.suggested_action,
        technical_detail=technical,
    )


def dashboard_issue_to_notice(issue: DashboardIssue) -> UserNotice:
    code = _DASHBOARD_CODE_ALIASES.get(issue.code, issue.code)
    if code in NOTICE_CATALOG:
        target_id = None
        detail = issue.detail
        if code in {"target_corrupt", "target_unreadable"}:
            target_id = _target_ids_from_detail(issue.detail)
        notice = build_notice(
            code,
            severity=_DASHBOARD_SEVERITY[issue.severity],
            target_id=target_id,
            detail=detail,
        )
        if issue.detail and code in {"invalid_config", "corrupt_journal", "operation_locked"}:
            return UserNotice(
                code=notice.code,
                severity=notice.severity,
                title=notice.title,
                explanation=issue.detail,
                suggested_action=notice.suggested_action,
                technical_detail=notice.technical_detail,
            )
        return notice
    return UserNotice(
        code=issue.code,
        severity=_DASHBOARD_SEVERITY[issue.severity],
        title=issue.title,
        explanation=issue.detail,
        suggested_action=issue.suggested_action,
        technical_detail=f"reason={issue.code}",
    )


_SKIP_REASON_CODES = {
    PushSkipReason.UNREADABLE: "target_unreadable",
    PushSkipReason.CORRUPT: "target_corrupt",
    PushSkipReason.RUNNING_APP: "application_running",
    PushSkipReason.BACKUP_FAILED: "backup_failed",
    PushSkipReason.BLOCKED_BY_USER: "update_blocked",
}


def skip_reason_to_notice_code(reason: str) -> str:
    lower = reason.lower().strip()
    mapped = _SKIP_REASON_CODES.get(lower)
    if mapped is not None:
        return mapped
    if "corrupt" in lower or "unsupported" in lower:
        return "target_corrupt"
    if "unreadable" in lower or "access" in lower:
        return "target_unreadable"
    if "running" in lower or "quit" in lower:
        return "application_running"
    if "backup" in lower:
        return "backup_failed"
    if "blocked" in lower:
        return "update_blocked"
    return "target_skipped"


def format_skip_status(reason: str) -> str:
    """Short chip for table cells — sentence detail stays in notice explanations."""
    code = skip_reason_to_notice_code(reason)
    chips = {
        "target_corrupt": "Skipped — corrupt",
        "target_unreadable": "Skipped — unreadable",
        "application_running": "Skipped — app was running",
        "backup_failed": "Skipped — backup failed",
        "update_blocked": "Skipped — not selected",
        "target_skipped": "Skipped",
    }
    return chips.get(code, "Skipped")


def format_notice_summary(notice: UserNotice) -> str:
    return notice.title


def format_notice_details(notice: UserNotice) -> str:
    return notice.explanation


def format_notice_action(notice: UserNotice) -> str:
    return notice.suggested_action or ""


def format_notice_technical(notice: UserNotice) -> str:
    if notice.technical_detail:
        return notice.technical_detail
    return f"reason={notice.code}"


def format_notice_block(notice: UserNotice, *, include_technical: bool = False) -> str:
    """User-visible notice block.

    Technical ``reason=...`` lines stay off by default (dashboard / guided UI).
    Pass ``include_technical=True`` for Health / support surfaces.
    """
    lines = [
        format_notice_summary(notice),
        "",
        format_notice_details(notice),
    ]
    action = format_notice_action(notice)
    if action:
        lines.extend(["", action])
    if include_technical:
        technical = format_notice_technical(notice)
        if technical:
            lines.extend(["", technical])
    return "\n".join(lines)


def _technical_detail(
    code: str,
    *,
    target_id: str | None,
    detail: str | None,
) -> str | None:
    parts = [f"reason={code}"]
    if target_id:
        parts.append(f"target={target_id}")
    if detail and code == "operation_locked":
        return None
    return " ".join(parts)


def _target_ids_from_detail(detail: str) -> str | None:
    marker = ": "
    if marker not in detail:
        return None
    suffix = detail.split(marker, maxsplit=1)[1].rstrip(".")
    names = [part.strip() for part in suffix.split(",") if part.strip()]
    if not names:
        return None
    return ",".join(_target_family(name) for name in names)


def _target_family(name: str) -> str:
    return dictionary_family_id(name)
