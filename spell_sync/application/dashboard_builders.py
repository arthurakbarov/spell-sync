"""Build UI-neutral dashboard and status-detail snapshots."""

from pathlib import Path

from ..dictionaries import Dictionary
from ..dictionary_hints import (
    EDITOR_FALLBACK,
    SUBLIME_NOT_FOUND,
    SUBLIME_USER_OVERRIDE,
    optional_app_warn_hints,
    project_honesty_warnings,
)
from ..operation_lock import OperationLockInfo
from ..project_setup.discovery import (
    _CONFIG_TARGET_IDS,
    dictionary_family_id,
    discover_setup_targets,
)
from ..push_journal import JournalLoadStatus
from ..read_outcome import ReadStatus, dictionary_read_result
from ..resolved_runtime import ResolvedRuntime
from ..settings import ConfigStatus
from ..sync_run import SyncRun
from ..workspace_git import inspect_workspace_git, workspace_git_dirty_message
from .product_concepts import (
    EMPTY_WORDLIST_WARN,
    apps_changed_phrase,
    dictionaries_updated_phrase,
)
from .reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetStatusRow,
)
from .user_notices import catalog_entry


def _overall_label(severity: DashboardSeverity) -> str:
    if severity is DashboardSeverity.BLOCKED:
        return "× Writes blocked"
    if severity is DashboardSeverity.WARNING:
        return "! Needs attention"
    return "✓ Ready"


def _max_severity(*severities: DashboardSeverity) -> DashboardSeverity:
    if DashboardSeverity.BLOCKED in severities:
        return DashboardSeverity.BLOCKED
    if DashboardSeverity.WARNING in severities:
        return DashboardSeverity.WARNING
    return DashboardSeverity.READY


def _dashboard_notice_text(code: str, *, detail: str | None = None) -> tuple[str, str, str]:
    template = catalog_entry(code)
    explanation = detail or template.explanation
    return template.title, explanation, template.suggested_action


def build_dashboard_issues(
    validated: ResolvedRuntime,
    snapshot: StatusSnapshot,
    *,
    lock_info: OperationLockInfo | None,
) -> tuple[DashboardIssue, ...]:
    issues: list[DashboardIssue] = []
    config_result = validated.config_result
    config_valid = config_result.status in (ConfigStatus.VALID, ConfigStatus.ABSENT)

    if not config_valid:
        detail = (
            config_result.diagnostics[0].message
            if config_result.diagnostics
            else config_result.status.value
        )
        title, explanation, action = _dashboard_notice_text("invalid_config", detail=detail)
        issues.append(
            DashboardIssue(
                code="invalid_config",
                severity=DashboardSeverity.BLOCKED,
                title=title,
                detail=explanation,
                suggested_action=action,
            )
        )

    if snapshot.wordlist_error is not None:
        title, explanation, action = _dashboard_notice_text("unreadable_wordlist")
        issues.append(
            DashboardIssue(
                code="unreadable_wordlist",
                severity=DashboardSeverity.BLOCKED,
                title=title,
                detail=explanation,
                suggested_action=action,
            )
        )

    journal = validated.journal_result
    if journal.status is JournalLoadStatus.VALID_IN_PROGRESS:
        title, explanation, action = _dashboard_notice_text("pending_recovery")
        issues.append(
            DashboardIssue(
                code="pending_recovery",
                severity=DashboardSeverity.BLOCKED,
                title=title,
                detail=explanation,
                suggested_action=action,
            )
        )
    elif journal.status is JournalLoadStatus.VALID_COMPLETED:
        title, explanation, action = _dashboard_notice_text("cleanup_pending")
        issues.append(
            DashboardIssue(
                code="cleanup_pending",
                severity=DashboardSeverity.WARNING,
                title=title,
                detail=explanation,
                suggested_action=action,
            )
        )
    elif journal.status in (
        JournalLoadStatus.CORRUPT,
        JournalLoadStatus.UNSUPPORTED_SCHEMA,
        JournalLoadStatus.UNSAFE_ARTIFACT,
    ):
        detail = journal.detail or journal.status.value
        title, explanation, action = _dashboard_notice_text("corrupt_journal", detail=detail)
        issues.append(
            DashboardIssue(
                code="corrupt_journal",
                severity=DashboardSeverity.BLOCKED,
                title=title,
                detail=explanation,
                suggested_action=action,
            )
        )

    if lock_info is not None:
        if lock_info.command in {"unsafe-lock", "unreadable-lock"}:
            issues.append(
                DashboardIssue(
                    code="operation_lock",
                    severity=DashboardSeverity.BLOCKED,
                    title="Project lock is not usable",
                    detail=(
                        "The project lock file is unsafe or unreadable. "
                        "Collect and Update will not start until it is fixed."
                    ),
                    suggested_action="Check .spell-sync.lock under the project directory.",
                )
            )
        else:
            title, explanation, action = _dashboard_notice_text("operation_locked")
            issues.append(
                DashboardIssue(
                    code="operation_lock",
                    severity=DashboardSeverity.BLOCKED,
                    title=title,
                    detail=(f"{explanation} ({lock_info.command}, pid {lock_info.pid})."),
                    suggested_action=action,
                )
            )

    if snapshot.skipped_corrupt:
        names = ", ".join(snapshot.skipped_corrupt)
        title, explanation, action = _dashboard_notice_text("target_corrupt")
        issues.append(
            DashboardIssue(
                code="corrupt_target",
                severity=DashboardSeverity.BLOCKED,
                title=title,
                detail=f"{explanation} Affected apps: {names}.",
                suggested_action=action,
            )
        )

    if snapshot.empty_wordlist and snapshot.wordlist_error is None:
        issues.append(
            DashboardIssue(
                code="empty_wordlist",
                severity=DashboardSeverity.WARNING,
                title="Word list is empty",
                detail="Update my apps will stop until words are added.",
                suggested_action="Open Add words to my list, or Collect my words.",
            )
        )

    if snapshot.skipped_unreadable:
        names = ", ".join(snapshot.skipped_unreadable)
        title, explanation, action = _dashboard_notice_text("target_unreadable")
        issues.append(
            DashboardIssue(
                code="skipped_unreadable",
                severity=DashboardSeverity.WARNING,
                title=title,
                detail=f"{explanation} Affected apps: {names}.",
                suggested_action=action,
            )
        )

    if snapshot.destructive_risk:
        issues.append(
            DashboardIssue(
                code="destructive_risk",
                severity=DashboardSeverity.WARNING,
                title="Destructive update risk",
                detail=snapshot.destructive_risk,
                suggested_action="Review the Update my apps preview before writing.",
            )
        )

    wordlist_path = validated.context.wordlist_file
    git_status = inspect_workspace_git(wordlist_path.parent)
    if git_status is not None and git_status.is_dirty:
        issues.append(
            DashboardIssue(
                code="workspace_git_dirty",
                severity=DashboardSeverity.WARNING,
                title="Personal Git changes uncommitted",
                detail=workspace_git_dirty_message(git_status),
                suggested_action="Run spell-sync git-save (add --push when an upstream exists).",
            )
        )

    for hint in optional_app_warn_hints(settings=validated.context.settings):
        if hint.code == SUBLIME_USER_OVERRIDE:
            issues.append(
                DashboardIssue(
                    code=SUBLIME_USER_OVERRIDE,
                    severity=DashboardSeverity.WARNING,
                    title="Sublime User Preferences override",
                    detail=hint.message,
                    suggested_action="Remove added_words from Sublime User Preferences.",
                )
            )
            continue
        if hint.code == SUBLIME_NOT_FOUND:
            issues.append(
                DashboardIssue(
                    code=SUBLIME_NOT_FOUND,
                    severity=DashboardSeverity.WARNING,
                    title="Sublime Text not found",
                    detail=hint.message,
                    suggested_action=("Install Sublime Text, or turn Sublime off in Applications."),
                )
            )
            continue
        if hint.code == EDITOR_FALLBACK:
            issues.append(
                DashboardIssue(
                    code=EDITOR_FALLBACK,
                    severity=DashboardSeverity.WARNING,
                    title="Code editor path uses the default",
                    detail=hint.message,
                    suggested_action=(
                        "Install a supported editor, or turn Editors off in Applications."
                    ),
                )
            )
            continue
        issues.append(
            DashboardIssue(
                code=hint.code or "optional_app_hint",
                severity=DashboardSeverity.WARNING,
                title=hint.message.split(" — ", 1)[0],
                detail=hint.message,
            )
        )

    return tuple(issues)


def _target_family_id(name: str) -> str:
    return dictionary_family_id(name)


def _compute_application_counts(
    validated: ResolvedRuntime,
    snapshot: StatusSnapshot,
) -> tuple[int, int, int, int]:
    settings = validated.context.settings
    enabled_ids = settings.enabled_dictionary_target_ids()
    discovery = discover_setup_targets(enabled_targets=enabled_ids)
    unreadable_ids = {_target_family_id(name) for name in snapshot.skipped_unreadable}
    corrupt_ids = {_target_family_id(name) for name in snapshot.skipped_corrupt}

    ready = 0
    needs_attention = 0
    disabled = 0
    unavailable = 0
    for target in discovery.targets:
        if target.identifier not in _CONFIG_TARGET_IDS:
            continue
        if not target.enabled:
            disabled += 1
            continue
        target_id = target.identifier
        if target_id in corrupt_ids or target_id in unreadable_ids:
            needs_attention += 1
        elif not target.detected:
            unavailable += 1
        elif target.available and target.readable:
            ready += 1
        else:
            needs_attention += 1
    return ready, needs_attention, disabled, unavailable


def format_dashboard_last_operation(record: object) -> str:
    from ..diagnostics.history_record import OperationHistoryRecord

    if not isinstance(record, OperationHistoryRecord):
        return ""
    operation_labels = {
        "pull": "Collect my words",
        "push": "Update my apps",
        "recover": "Recovery",
        "setup": "Setup",
        "targets": "Applications",
    }
    operation = operation_labels.get(record.operation, record.operation.replace("_", " ").title())
    outcome = record.outcome.replace("_", " ").title()
    if record.operation == "pull" and record.added_words:
        detail = f"{record.added_words} words added"
    elif record.operation == "push" and record.updated_targets:
        detail = dictionaries_updated_phrase(record.updated_targets)
    elif record.operation == "setup" and record.created_files:
        detail = f"{record.created_files} files created"
    elif record.operation == "recover" and record.restored_files:
        detail = f"{record.restored_files} files restored"
    elif record.operation == "targets" and record.updated_targets:
        detail = apps_changed_phrase(record.updated_targets)
    else:
        detail = outcome
    warning = " (warnings)" if record.warnings else ""
    return f"Last: {operation} — {detail}{warning}"


def build_dashboard_state(
    validated: ResolvedRuntime,
    snapshot: StatusSnapshot,
    *,
    lock_info: OperationLockInfo | None,
    last_operation_summary: str | None = None,
) -> DashboardState:
    project = validated.context.project_dir
    wordlist = validated.context.wordlist_file
    issues = build_dashboard_issues(validated, snapshot, lock_info=lock_info)
    issue_severities = tuple(issue.severity for issue in issues)
    overall = _max_severity(*issue_severities) if issue_severities else DashboardSeverity.READY
    unreadable = set(snapshot.skipped_unreadable)
    corrupt = set(snapshot.skipped_corrupt)
    detected = len(validated.context.dictionaries) + len(unreadable) + len(corrupt)
    enabled = len(validated.context.dictionaries) + len(unreadable) + len(corrupt)
    available = len(validated.context.dictionaries)
    pending_recovery = validated.journal_result.status is JournalLoadStatus.VALID_IN_PROGRESS
    config_status = validated.config_result.status.value
    config_valid = validated.config_result.status in (ConfigStatus.VALID, ConfigStatus.ABSENT)
    targets_ready, targets_needs_attention, targets_disabled, targets_unavailable = (
        _compute_application_counts(validated, snapshot)
    )

    return DashboardState(
        wordlist_path=str(wordlist),
        project_dir=str(project),
        config_status=config_status,
        config_valid=config_valid,
        targets_detected=detected,
        targets_enabled=enabled,
        targets_available=available,
        targets_ready=targets_ready,
        targets_needs_attention=targets_needs_attention,
        targets_disabled=targets_disabled,
        targets_unavailable=targets_unavailable,
        pending_recovery=pending_recovery,
        overall_severity=overall,
        overall_label=_overall_label(overall),
        issues=issues,
        snapshot=snapshot,
        last_operation_summary=last_operation_summary,
    )


def _target_row_from_dictionary(dictionary: Dictionary) -> TargetStatusRow:
    read_result = dictionary_read_result(dictionary)
    available = read_result.status is ReadStatus.OK
    return TargetStatusRow(
        name=dictionary.name,
        enabled=True,
        available=available,
        read_status=read_result.status.value,
        path=dictionary.path,
        format=dictionary.format.value,
        word_count=len(read_result.words) if read_result.status is ReadStatus.OK else None,
        detail=read_result.detail,
    )


def _target_row_skipped(name: str, *, reason: str, detail: str) -> TargetStatusRow:
    return TargetStatusRow(
        name=name,
        enabled=True,
        available=False,
        read_status=reason,
        path="",
        format="",
        word_count=None,
        detail=detail,
        skipped_reason=reason,
    )


def build_status_detail_snapshot(run: SyncRun) -> StatusDetailSnapshot:
    ctx = run.context
    wordlist_error = run.check_wordlist()
    skipped_unreadable = run.skipped_unreadable_dictionary_names()
    skipped_corrupt = run.skipped_corrupt_dictionary_names()
    word_count = 0
    empty_wordlist = False
    destructive_risk = None
    if wordlist_error is None:
        word_count = len(run.load_wordlist())
        empty_wordlist = word_count == 0
        destructive_risk = run.destructive_push_risk()

    rows: list[TargetStatusRow] = []
    skipped_names = set(skipped_unreadable) | set(skipped_corrupt)
    for dictionary in run.dictionaries:
        if dictionary.name in skipped_names:
            continue
        rows.append(_target_row_from_dictionary(dictionary))
    seen_skipped: set[str] = set()
    for name in skipped_unreadable:
        if name in seen_skipped:
            continue
        seen_skipped.add(name)
        rows.append(
            _target_row_skipped(
                name,
                reason="unreadable",
                detail="Dictionary read failed (permissions or missing path).",
            )
        )
    for name in skipped_corrupt:
        if name in seen_skipped:
            continue
        seen_skipped.add(name)
        rows.append(
            _target_row_skipped(
                name,
                reason="corrupt",
                detail="Dictionary is corrupt or unsupported.",
            )
        )

    warnings: list[str] = []
    if empty_wordlist:
        warnings.append(EMPTY_WORDLIST_WARN)
    warnings.extend(project_honesty_warnings(Path(run.wordlist_str), settings=run.context.settings))

    return StatusDetailSnapshot(
        wordlist_path=run.wordlist_str,
        project_dir=str(ctx.project_dir),
        config_path=str(ctx.config_path) if ctx.config_path.is_file() else None,
        wordlist_count=word_count,
        targets=tuple(rows),
        skipped_unreadable=skipped_unreadable,
        skipped_corrupt=skipped_corrupt,
        wordlist_error=wordlist_error,
        destructive_risk=destructive_risk,
        warnings=tuple(warnings),
    )
