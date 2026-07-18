"""Build UI-neutral dashboard, status, preview, and doctor snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..dictionaries import Dictionary
from ..exit_codes import ExitCode
from ..health.types import DoctorAction, DoctorCheck, DoctorReport
from ..operation_lock import OperationLockInfo
from ..push_journal import (
    JOURNAL_STATE_ROLLBACK_INCOMPLETE,
    JournalLoadStatus,
    file_content_hash,
    plan_recovery_from_journal,
)
from ..push_prepared import PreparedPush
from ..read_outcome import ReadStatus, dictionary_read_result
from ..settings import ConfigStatus
from ..sync_models import PushResult
from ..sync_run import SyncRun
from ..validated_runtime import ValidatedRuntime
from .reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PullSourcePreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryItemPreview,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetPreview,
    TargetStatusRow,
    TargetUpdateReport,
)


def _overall_label(severity: DashboardSeverity) -> str:
    if severity is DashboardSeverity.BLOCKED:
        return "× Writes blocked"
    if severity is DashboardSeverity.WARNING:
        return "! Attention required"
    return "✓ Ready"


def _max_severity(*severities: DashboardSeverity) -> DashboardSeverity:
    if DashboardSeverity.BLOCKED in severities:
        return DashboardSeverity.BLOCKED
    if DashboardSeverity.WARNING in severities:
        return DashboardSeverity.WARNING
    return DashboardSeverity.READY


def build_dashboard_issues(
    validated: ValidatedRuntime,
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
        issues.append(
            DashboardIssue(
                code="invalid_config",
                severity=DashboardSeverity.BLOCKED,
                title="Invalid configuration",
                detail=detail,
                suggested_action="Fix spell-sync.toml, then run spell-sync config-check.",
            )
        )

    if snapshot.wordlist_error is not None:
        issues.append(
            DashboardIssue(
                code="unreadable_wordlist",
                severity=DashboardSeverity.BLOCKED,
                title="Wordlist unreadable",
                detail=f"Wordlist check failed with exit {int(snapshot.wordlist_error)}.",
                suggested_action="Check file permissions and path, then run spell-sync doctor.",
            )
        )

    journal = validated.journal_result
    if journal.status is JournalLoadStatus.VALID_IN_PROGRESS:
        issues.append(
            DashboardIssue(
                code="pending_recovery",
                severity=DashboardSeverity.BLOCKED,
                title="Pending recovery",
                detail="An unfinished push journal requires recovery before writes.",
                suggested_action="Run spell-sync recover before push or pull.",
            )
        )
    elif journal.status in (
        JournalLoadStatus.CORRUPT,
        JournalLoadStatus.UNSUPPORTED_SCHEMA,
    ):
        detail = journal.detail or journal.status.value
        issues.append(
            DashboardIssue(
                code="corrupt_journal",
                severity=DashboardSeverity.BLOCKED,
                title="Corrupt push journal",
                detail=detail,
                suggested_action="Inspect the journal file or run spell-sync recover.",
            )
        )

    if lock_info is not None:
        issues.append(
            DashboardIssue(
                code="operation_lock",
                severity=DashboardSeverity.BLOCKED,
                title="Operation lock active",
                detail=(
                    f"Another spell-sync process holds the lock "
                    f"({lock_info.command}, pid {lock_info.pid})."
                ),
                suggested_action="Wait for the other process to finish.",
            )
        )

    if snapshot.skipped_corrupt:
        names = ", ".join(snapshot.skipped_corrupt)
        issues.append(
            DashboardIssue(
                code="corrupt_target",
                severity=DashboardSeverity.BLOCKED,
                title="Dictionary target damaged",
                detail=f"Corrupt or unsupported dictionaries: {names}.",
                suggested_action="Repair dictionary files or disable targets in config.",
            )
        )

    if snapshot.empty_wordlist and snapshot.wordlist_error is None:
        issues.append(
            DashboardIssue(
                code="empty_wordlist",
                severity=DashboardSeverity.WARNING,
                title="Wordlist is empty",
                detail="Push will abort until words are added.",
                suggested_action="Add words or run spell-sync pull.",
            )
        )

    if snapshot.skipped_unreadable:
        names = ", ".join(snapshot.skipped_unreadable)
        issues.append(
            DashboardIssue(
                code="skipped_unreadable",
                severity=DashboardSeverity.WARNING,
                title="Unreadable dictionary targets",
                detail=f"Read failed for: {names}.",
                suggested_action="Check permissions or disable affected targets.",
            )
        )

    if snapshot.destructive_risk:
        issues.append(
            DashboardIssue(
                code="destructive_risk",
                severity=DashboardSeverity.WARNING,
                title="Destructive push risk",
                detail=snapshot.destructive_risk,
                suggested_action="Review push preview before writing.",
            )
        )

    return tuple(issues)


def build_dashboard_state(
    validated: ValidatedRuntime,
    snapshot: StatusSnapshot,
    *,
    lock_info: OperationLockInfo | None,
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

    return DashboardState(
        wordlist_path=str(wordlist),
        project_dir=str(project),
        config_status=config_status,
        config_valid=config_valid,
        targets_detected=detected,
        targets_enabled=enabled,
        targets_available=available,
        pending_recovery=pending_recovery,
        overall_severity=overall,
        overall_label=_overall_label(overall),
        issues=issues,
        snapshot=snapshot,
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
    snapshot = StatusSnapshot(
        wordlist_count=0,
        diffs=tuple(run.status_diffs()),
        skipped_unreadable=run.skipped_unreadable_dictionary_names(),
        skipped_corrupt=run.skipped_corrupt_dictionary_names(),
        wordlist_error=run.check_wordlist(),
        destructive_risk=run.destructive_push_risk(),
        empty_wordlist=False,
    )
    wordlist_error = snapshot.wordlist_error
    word_count = 0
    if wordlist_error is None:
        word_count = len(run.load_wordlist())
        snapshot = StatusSnapshot(
            wordlist_count=word_count,
            diffs=snapshot.diffs,
            skipped_unreadable=snapshot.skipped_unreadable,
            skipped_corrupt=snapshot.skipped_corrupt,
            wordlist_error=None,
            destructive_risk=snapshot.destructive_risk,
            empty_wordlist=word_count == 0,
        )

    rows: list[TargetStatusRow] = [_target_row_from_dictionary(d) for d in run.dictionaries]
    for name in snapshot.skipped_unreadable:
        rows.append(
            _target_row_skipped(
                name,
                reason="unreadable",
                detail="Dictionary read failed (permissions or missing path).",
            )
        )
    for name in snapshot.skipped_corrupt:
        rows.append(
            _target_row_skipped(
                name,
                reason="corrupt",
                detail="Dictionary is corrupt or unsupported.",
            )
        )

    return StatusDetailSnapshot(
        wordlist_path=run.wordlist_str,
        project_dir=str(ctx.project_dir),
        config_paths=tuple(str(path) for path in ctx.config_paths),
        wordlist_count=word_count,
        targets=tuple(rows),
        skipped_unreadable=snapshot.skipped_unreadable,
        skipped_corrupt=snapshot.skipped_corrupt,
        wordlist_error=wordlist_error,
        destructive_risk=snapshot.destructive_risk,
    )


def _plan_identifier(prepared: PreparedPush) -> str:
    wordlist_path = Path(prepared.ctx.wordlist_str)
    try:
        if prepared.wordlist_rendered is not None:
            return prepared.wordlist_rendered.sha256[:8]
        digest = file_content_hash(wordlist_path)
        if digest:
            return digest[:8]
    except OSError:
        pass
    return f"{len(prepared.targets)}targets"


def _target_preview_status(additions: int, removals: int) -> str:
    if additions == 0 and removals == 0:
        return "Unchanged"
    if removals > 0:
        return "Review"
    return "Ready"


def build_push_preview(
    prepared: PreparedPush | None,
    *,
    prepare_error: ExitCode | None = None,
    wordlist_error: ExitCode | None = None,
) -> PushPreview:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if wordlist_error is not None:
        return PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at=created_at,
            plan_identifier="unavailable",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            wordlist_error=wordlist_error,
        )
    if prepare_error is not None or prepared is None:
        return PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at=created_at,
            plan_identifier="blocked",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            prepare_error=prepare_error,
        )

    targets: list[TargetPreview] = []
    total_add = 0
    total_remove = 0
    to_update = 0
    unchanged = 0
    for item in prepared.targets:
        additions = len(item.planned.additions)
        removals = len(item.planned.removals)
        total_add += additions
        total_remove += removals
        status = _target_preview_status(additions, removals)
        if status == "Unchanged":
            unchanged += 1
        else:
            to_update += 1
        targets.append(
            TargetPreview(
                name=item.planned.dictionary.name,
                additions=additions,
                removals=removals,
                status=status,
                removal_words=item.planned.removals,
            )
        )

    warnings: list[str] = []
    if prepared.skipped_unreadable:
        warnings.append(f"Skipped unreadable: {', '.join(prepared.skipped_unreadable)}")
    if prepared.skipped_corrupt:
        warnings.append(f"Skipped corrupt: {', '.join(prepared.skipped_corrupt)}")
    if prepared.skipped_blocked:
        warnings.append(f"Skipped blocked: {', '.join(prepared.skipped_blocked)}")

    return PushPreview(
        prepared=prepared,
        targets=tuple(targets),
        additions=total_add,
        removals=total_remove,
        warnings=tuple(warnings),
        created_at=created_at,
        plan_identifier=_plan_identifier(prepared),
        targets_to_update=to_update,
        unchanged=unchanged,
        skipped=prepared.skipped_unreadable,
        corrupt=prepared.skipped_corrupt,
        blocked=prepared.skipped_blocked,
    )


def _doctor_level(level: str) -> str:
    if level == "error":
        return "failed"
    if level == "warn":
        return "warning"
    return "passed"


def _doctor_group(message: str) -> str:
    lower = message.lower()
    if message.startswith("config:") or "spell-sync.toml" in lower:
        return "Configuration"
    if "wordlist" in lower:
        return "Wordlist"
    if "journal" in lower or "transaction" in lower or "recover" in lower:
        return "Transaction state"
    if any(token in lower for token in ("dictionary", "chrome", "firefox", "hunspell")):
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
    for action in actions:
        if action.reason.lower() in check.message.lower():
            if action.command:
                return action.command
            if action.hint:
                return action.hint
    return None


def build_doctor_snapshot(report: DoctorReport) -> DoctorSnapshot:
    checks: list[DoctorCheckView] = []
    for check in report.checks:
        checks.append(
            DoctorCheckView(
                group=_doctor_group(check.message),
                level=_doctor_level(check.level),
                title=check.message.split(".", maxsplit=1)[0],
                detail=check.message,
                suggested_action=_suggested_action_for_check(check, report.actions),
            )
        )
    if report.dictionaries_total and report.dictionaries_readable < report.dictionaries_total:
        unreadable = report.dictionaries_total - report.dictionaries_readable
        checks.append(
            DoctorCheckView(
                group="Dictionaries",
                level="warning",
                title="Some dictionaries are unreadable",
                detail=(
                    f"{report.dictionaries_readable}/{report.dictionaries_total} "
                    f"dictionaries readable ({unreadable} unreadable)."
                ),
                suggested_action="Grant file access or disable unreadable targets.",
            )
        )
    if report.dictionaries_writable < report.dictionaries_readable:
        checks.append(
            DoctorCheckView(
                group="Filesystem access",
                level="warning",
                title="Some dictionaries are not writable",
                detail=(
                    f"{report.dictionaries_writable}/{report.dictionaries_readable} "
                    "readable dictionaries are writable."
                ),
                suggested_action="Check permissions before push.",
            )
        )
    for name in report.skipped_unreadable:
        checks.append(
            DoctorCheckView(
                group="Dictionaries",
                level="warning",
                title=f"Skipped unreadable target: {name}",
                detail="Dictionary path could not be read during discovery.",
                suggested_action="Verify path permissions.",
            )
        )
    return DoctorSnapshot(checks=tuple(checks), has_errors=report.has_errors)


def build_pull_preview(run: SyncRun) -> PullPreview:
    """Compute pull merge without writing the wordlist."""
    from ..io import read_text_words
    from ..read_outcome import is_readable_for_union
    from ..words import clean_words, merge_case_duplicates, sort_words

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    wordlist_path = run.wordlist_str
    wordlist_error = run.check_wordlist()
    if wordlist_error is not None:
        return PullPreview(
            wordlist_path=wordlist_path,
            additions=0,
            before_count=0,
            after_count=0,
            sources_used=(),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at=created_at,
            plan_identifier="unavailable",
            merged_words=(),
            wordlist_error=wordlist_error,
        )

    words = clean_words(read_text_words(wordlist_path))
    before = len(words)
    ordered = sort_words(words)
    seen_casefold = {word.casefold() for word in ordered}
    addition_words: set[str] = set()
    sources_used: list[str] = []
    sources_skipped: list[str] = []
    source_rows: list[PullSourcePreview] = []
    warnings: list[str] = []

    for dictionary in run.context.dictionaries:
        read_result = dictionary_read_result(dictionary)
        status = read_result.status
        if status is ReadStatus.UNREADABLE:
            sources_skipped.append(dictionary.name)
            source_rows.append(
                PullSourcePreview(
                    dictionary.name,
                    "skipped",
                    detail="no access — pull skipped",
                )
            )
            warnings.append(f"Skipped unreadable: {dictionary.name}")
            continue
        if status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
            sources_skipped.append(dictionary.name)
            source_rows.append(
                PullSourcePreview(
                    dictionary.name,
                    "skipped",
                    detail="corrupt or unsupported — pull skipped",
                )
            )
            warnings.append(f"Skipped corrupt: {dictionary.name}")
            continue
        if not is_readable_for_union(status):
            sources_skipped.append(dictionary.name)
            source_rows.append(PullSourcePreview(dictionary.name, "skipped", detail=status.value))
            continue
        contributed = 0
        for word in sort_words(read_result.words):
            key = word.casefold()
            if key not in seen_casefold:
                ordered.append(word)
                seen_casefold.add(key)
                addition_words.add(word)
                contributed += 1
        sources_used.append(dictionary.name)
        source_rows.append(
            PullSourcePreview(
                dictionary.name,
                "used",
                words_contributed=contributed,
            )
        )

    merged = merge_case_duplicates(ordered)
    after = len(merged)
    digest = file_content_hash(Path(wordlist_path))
    plan_id = (digest or f"{before}-{after}")[:8]
    return PullPreview(
        wordlist_path=wordlist_path,
        additions=after - before,
        before_count=before,
        after_count=after,
        sources_used=tuple(sources_used),
        sources_skipped=tuple(sources_skipped),
        source_rows=tuple(source_rows),
        warnings=tuple(warnings),
        created_at=created_at,
        plan_identifier=plan_id,
        merged_words=tuple(merged),
        addition_words=frozenset(addition_words),
        wordlist_fingerprint=digest,
    )


def build_target_updates_from_preview(preview: PushPreview) -> tuple[TargetUpdateReport, ...]:
    rows: list[TargetUpdateReport] = []
    for target in preview.targets:
        rows.append(
            TargetUpdateReport(
                name=target.name,
                additions=target.additions,
                removals=target.removals,
                status=target.status,
            )
        )
    for name in preview.skipped:
        rows.append(TargetUpdateReport(name=name, additions=0, removals=0, status="Skipped"))
    for name in preview.corrupt:
        rows.append(TargetUpdateReport(name=name, additions=0, removals=0, status="Corrupt"))
    return tuple(rows)


def build_push_operation_report(execution: PushExecution) -> OperationReport:
    outcome = execution.outcome
    if outcome is OperationOutcome.RECOVERY_REQUIRED:
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Push requires recovery",
            summary=(
                "Automatic rollback was incomplete. Recovery metadata and snapshots were preserved."
            ),
            details=(
                "Run Recovery before another write operation.",
                execution.message,
            ),
            target_updates=execution.target_updates,
            warnings=execution.warnings,
            recovery_required=True,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.STOPPED_SAFELY:
        if execution.conflict_target:
            return OperationReport(
                operation="push",
                outcome=outcome,
                title="Push stopped safely",
                summary=(
                    "A target changed after the preview was created. "
                    "The conflicting file was not overwritten."
                ),
                details=(
                    f"Conflicting target: {execution.conflict_target}",
                    "No conflicting file was overwritten.",
                ),
                conflict_target=execution.conflict_target,
                plan_identifier=execution.plan_identifier,
            )
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Push stopped safely",
            summary="A write failed. Previously updated files were restored.",
            details=(execution.message,),
            target_updates=execution.target_updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.COMPLETED_WITH_WARNINGS:
        result = execution.result
        skipped = len(result.skipped) if isinstance(result, PushResult) else 0
        written = len(result.written) if isinstance(result, PushResult) else 0
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Push completed with warnings",
            summary=f"{written} targets updated, {skipped} target(s) skipped.",
            details=(execution.message,),
            target_updates=execution.target_updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.COMPLETED:
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Push completed",
            summary=execution.message or "Push finished successfully.",
            details=("Transaction: completed", "Recovery data: cleaned up"),
            target_updates=execution.target_updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    return OperationReport(
        operation="push",
        outcome=outcome,
        title="Push failed",
        summary=execution.message or "Push could not complete.",
        details=(),
        target_updates=execution.target_updates,
        warnings=execution.warnings,
        plan_identifier=execution.plan_identifier,
    )


def build_pull_operation_report(execution: PullExecution) -> OperationReport:
    preview = execution.preview
    if execution.outcome is OperationOutcome.COMPLETED:
        return OperationReport(
            operation="pull",
            outcome=execution.outcome,
            title="Pull completed",
            summary=(f"{preview.additions} words added to the canonical wordlist"),
            details=(
                f"{len(preview.sources_used)} sources read",
                f"{len(preview.sources_skipped)} source(s) skipped",
                f"Wordlist: {preview.wordlist_path}",
            ),
            warnings=execution.warnings or preview.warnings,
            plan_identifier=preview.plan_identifier,
        )
    return OperationReport(
        operation="pull",
        outcome=execution.outcome,
        title="Pull failed",
        summary=execution.message or "Pull could not complete.",
        details=(f"Wordlist: {preview.wordlist_path}",),
        warnings=execution.warnings,
        plan_identifier=preview.plan_identifier,
    )


def _empty_recovery_preview(
    *,
    status: RecoveryStatus,
    wordlist_path: str,
    detail: str | None = None,
    can_discard: bool = False,
) -> RecoveryPreview:
    return RecoveryPreview(
        status=status,
        transaction_id="",
        command="",
        transaction_state="",
        started_at="",
        wordlist_path=wordlist_path,
        snapshot_directory=None,
        items=(),
        recoverable_count=0,
        conflict_count=0,
        failure_count=0,
        warnings=(),
        can_recover=False,
        can_discard=can_discard,
        can_cleanup=False,
        snapshots_valid=True,
        preview_fingerprint="absent",
        detail=detail,
    )


def build_recovery_preview(validated: ValidatedRuntime) -> RecoveryPreview:
    wordlist_path = str(validated.context.wordlist_file)
    journal_result = validated.journal_result
    status = journal_result.status

    if status is JournalLoadStatus.ABSENT:
        return _empty_recovery_preview(
            status=RecoveryStatus.ABSENT,
            wordlist_path=wordlist_path,
            detail="No unfinished transaction was found.",
        )
    if status is JournalLoadStatus.CORRUPT:
        return _empty_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            wordlist_path=wordlist_path,
            detail=journal_result.detail or status.value,
            can_discard=True,
        )
    if status is JournalLoadStatus.UNSUPPORTED_SCHEMA:
        return _empty_recovery_preview(
            status=RecoveryStatus.UNSUPPORTED_SCHEMA,
            wordlist_path=wordlist_path,
            detail=journal_result.detail or status.value,
        )

    journal = journal_result.journal
    assert journal is not None
    if status is JournalLoadStatus.VALID_COMPLETED:
        return RecoveryPreview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            transaction_id=journal.transaction_id,
            command=journal.command,
            transaction_state=journal.state,
            started_at=journal.started,
            wordlist_path=wordlist_path,
            snapshot_directory=journal.snapshot_dir,
            items=(),
            recoverable_count=0,
            conflict_count=0,
            failure_count=0,
            warnings=("The transaction completed successfully, but recovery artifacts remain.",),
            can_recover=False,
            can_discard=True,
            can_cleanup=True,
            snapshots_valid=True,
            preview_fingerprint=journal.transaction_id,
            detail="Only cleanup is required.",
        )

    plans = plan_recovery_from_journal(journal)
    items = tuple(
        RecoveryItemPreview(
            name=plan.name,
            path=plan.path,
            current_state=plan.current_state,
            recovery_action=plan.recovery_action,
            status=plan.status,
            detail=plan.detail,
            existed_before=plan.existed_before,
            write_started=plan.write_started,
            write_completed=plan.write_completed,
            snapshot_valid=plan.snapshot_valid,
        )
        for plan in plans
    )
    recoverable_count = sum(1 for item in items if item.status == "ready")
    conflict_count = sum(1 for item in items if item.status == "conflict")
    failure_count = sum(1 for item in items if item.status == "failed")
    snapshots_valid = all(
        item.snapshot_valid or item.status in {"skipped", "conflict"} for item in items
    )
    warnings: list[str] = []
    if journal.state == JOURNAL_STATE_ROLLBACK_INCOMPLETE:
        warnings.append("Automatic rollback was incomplete.")
    if failure_count:
        warnings.append(f"{failure_count} item(s) have invalid snapshots.")
    if conflict_count:
        warnings.append(f"{conflict_count} item(s) have external conflicts.")

    if journal.state == JOURNAL_STATE_ROLLBACK_INCOMPLETE:
        recovery_status = RecoveryStatus.RECOVERY_IN_PROGRESS
    elif conflict_count and recoverable_count == 0:
        recovery_status = RecoveryStatus.CONFLICTED
    elif conflict_count:
        recovery_status = RecoveryStatus.CONFLICTED
    else:
        recovery_status = RecoveryStatus.RECOVERABLE

    can_recover = recoverable_count > 0 and snapshots_valid and failure_count == 0
    return RecoveryPreview(
        status=recovery_status,
        transaction_id=journal.transaction_id,
        command=journal.command,
        transaction_state=journal.state,
        started_at=journal.started,
        wordlist_path=wordlist_path,
        snapshot_directory=journal.snapshot_dir,
        items=items,
        recoverable_count=recoverable_count,
        conflict_count=conflict_count,
        failure_count=failure_count,
        warnings=tuple(warnings),
        can_recover=can_recover,
        can_discard=False,
        can_cleanup=False,
        snapshots_valid=snapshots_valid,
        preview_fingerprint=journal.transaction_id,
    )


def build_recovery_operation_report(execution: RecoveryExecution) -> OperationReport:
    outcome = execution.outcome
    if outcome is RecoveryOutcome.RECOVERED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title="Recovery completed",
            summary=execution.message,
            details=(
                f"Restored: {len(execution.restored)}",
                f"Skipped: {len(execution.skipped)}",
                "Recovery metadata: cleaned up",
            ),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.RECOVERED_WITH_WARNINGS:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
            title="Recovery completed with warnings",
            summary=execution.message,
            details=tuple(execution.warnings),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.CONFLICTED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Recovery stopped safely",
            summary=execution.message,
            details=(
                "Recovery metadata and snapshots were preserved.",
                *(f"Conflict: {name}" for name in execution.conflicts),
            ),
            warnings=execution.warnings,
            recovery_required=True,
        )
    if outcome is RecoveryOutcome.RECOVERY_INCOMPLETE:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Recovery is incomplete",
            summary=execution.message,
            details=(
                "Recovery metadata and snapshots were preserved.",
                "Run Recovery again after resolving the failure.",
            ),
            warnings=execution.warnings,
            recovery_required=True,
        )
    if outcome is RecoveryOutcome.CLEANUP_COMPLETED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title="Transaction cleanup completed",
            summary=execution.message,
            details=("Remaining recovery artifacts were removed.",),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.DISCARDED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title="Recovery metadata discarded",
            summary=execution.message,
            details=(
                "No files were restored.",
                "The current filesystem state was kept.",
            ),
            warnings=execution.warnings,
        )
    return OperationReport(
        operation="recover",
        outcome=OperationOutcome.FAILED,
        title="Recovery failed",
        summary=execution.message,
        details=(),
        warnings=execution.warnings,
        recovery_required=True,
    )


def build_setup_operation_report(execution) -> OperationReport:
    from ..project_setup.execute import ProjectSetupOutcome

    prepared = execution.prepared
    if execution.outcome is ProjectSetupOutcome.COMPLETED:
        details = [
            f"Canonical wordlist: {prepared.wordlist_path}",
            f"Configuration: {prepared.config_path}",
            f"Enabled targets: {len(prepared.enabled_targets)}",
            "No application dictionaries were changed.",
        ]
        if prepared.existing_wordlist_kept:
            details.insert(1, "The existing canonical wordlist was kept unchanged.")
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.COMPLETED,
            title="Project created",
            summary=execution.message,
            details=tuple(details),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    if execution.outcome is ProjectSetupOutcome.STOPPED_SAFELY:
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Project creation stopped safely",
            summary=execution.message,
            details=("No existing file was overwritten.",),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    if execution.outcome is ProjectSetupOutcome.SETUP_INCOMPLETE:
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.FAILED,
            title="Project setup is incomplete",
            summary=execution.message,
            details=(
                "Some newly created files could not be removed after an error.",
                "Existing files were not overwritten.",
            ),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    return OperationReport(
        operation="setup",
        outcome=OperationOutcome.FAILED,
        title="Project setup failed",
        summary=execution.message,
        details=(),
        warnings=execution.warnings,
        plan_identifier=prepared.setup_id,
    )
