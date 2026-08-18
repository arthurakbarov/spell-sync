"""Build the UI-neutral doctor snapshot."""

from ..health.types import DoctorAction, DoctorCheck, DoctorReport
from .reports import DoctorCheckView, DoctorSnapshot


def _doctor_level(level: str) -> str:
    if level == "error":
        return "failed"
    if level == "warn":
        return "warning"
    if level == "info":
        return "info"
    return "passed"


def _doctor_group(message: str) -> str:
    lower = message.lower()
    if message.startswith("config:") or "spell-sync.toml" in lower:
        return "Configuration"
    if "wordlist" in lower or "word list" in lower:
        return "Word list"
    if (
        "journal" in lower
        or "transaction" in lower
        or "recover" in lower
        or "interrupted update" in lower
        or "interrupted-update" in lower
    ):
        return "Interrupted update"
    if any(
        token in lower
        for token in ("dictionary", "chrome", "firefox", "hunspell", "sublime", "editor")
    ):
        return "Dictionaries"
    if "access" in lower or "permission" in lower or "disk" in lower:
        return "Filesystem access"
    if "lock" in lower or "hook" in lower or "cli" in lower:
        return "Project"
    return "Project"


def _suggested_action_for_check(
    check: DoctorCheck,
    actions: tuple[DoctorAction, ...],
) -> str | None:
    """Map doctor checks to actions by stable action id needles (not fragile full reasons)."""
    needles_by_id: dict[str, tuple[str, ...]] = {
        "recover-push": ("interrupted update", "interrupted-update", "push journal"),
        "recover-cleanup": ("recovery files remain", "completed update leftovers"),
        "add-words": ("wordlist is empty", "word list is empty"),
        "path-export": ("not on path",),
        "macos-fda": ("applespell", "full disk access"),
        "reinstall-hooks": ("hook is outdated", "outdated"),
        "install-hooks": ("missing pre-push", "missing pre-commit", "missing pre-"),
    }
    lower = check.message.lower()
    for action in actions:
        needles = needles_by_id.get(action.id, (action.reason,))
        if any(needle.lower() in lower for needle in needles):
            if action.command:
                return action.command
            if action.hint:
                return action.hint
            if action.shell:
                return action.shell
    return None


def build_doctor_snapshot(report: DoctorReport) -> DoctorSnapshot:
    checks = [
        DoctorCheckView(
            group=_doctor_group(check.message),
            level=_doctor_level(check.level),
            title=check.message.split(".", maxsplit=1)[0],
            detail=check.message,
            suggested_action=_suggested_action_for_check(check, report.actions),
        )
        for check in report.checks
    ]
    return DoctorSnapshot(checks=tuple(checks), has_errors=report.has_errors)
