"""Redacted support report model and export."""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..application.project_resolution import resolve_project_wordlist
from ..application.requests import SupportReportRequest
from ..command_helpers import sync_run_for
from ..diagnostics.paths import resolve_app_state_paths
from ..project_setup.target_settings import load_target_settings_snapshot
from ..push_journal import JournalLoadStatus, load_journal_result
from ..runtime import installed_package_version
from ..settings import ConfigStatus
from ..support.path_redaction import redact_text
from ..validated_runtime import build_validated_runtime
from .target_details import build_target_details


@dataclass(frozen=True)
class PrivacyManifest:
    contains_words: bool = False
    contains_dictionary_contents: bool = False
    contains_config_contents: bool = False
    paths_redacted: bool = True
    profile_names_redacted: bool = True


@dataclass(frozen=True)
class SupportNotice:
    code: str
    title: str
    explanation: str
    suggested_action: str | None


@dataclass(frozen=True)
class SupportOperationSummary:
    operation: str
    outcome: str
    timestamp: str
    record_id: str


@dataclass(frozen=True)
class TargetSupportState:
    identifier: str
    display_name: str
    enabled: bool
    detected: bool
    readable: bool
    writable: bool
    runtime_state: str
    reason_code: str | None


@dataclass(frozen=True)
class RecoverySupportState:
    pending_recovery: bool
    journal_status: str


@dataclass(frozen=True)
class ProjectSupportState:
    config_valid: bool
    wordlist_count: int | None
    pending_recovery: bool


@dataclass(frozen=True)
class InstallationInfo:
    package_version: str
    installation_type: str


@dataclass(frozen=True)
class SupportReport:
    schema_version: int
    generated_at: datetime
    spell_sync_version: str
    python_version: str
    operating_system: str
    architecture: str
    installation: InstallationInfo
    project: ProjectSupportState
    targets: tuple[TargetSupportState, ...]
    recovery: RecoverySupportState
    recent_operations: tuple[SupportOperationSummary, ...]
    notices: tuple[SupportNotice, ...]
    privacy: PrivacyManifest


def build_support_report(service: object, request: SupportReportRequest) -> SupportReport:
    wordlist = resolve_project_wordlist(request.project)
    validated = build_validated_runtime(wordlist)
    config_valid = validated.config_result.status in (ConfigStatus.VALID, ConfigStatus.ABSENT)
    word_count: int | None = None
    try:
        run = sync_run_for(wordlist)
        word_count = len(run.load_wordlist())
    except Exception:
        word_count = None
    journal = load_journal_result(wordlist)
    pending = journal.status is JournalLoadStatus.VALID_IN_PROGRESS

    target_settings = load_target_settings_snapshot(wordlist=wordlist)
    targets: list[TargetSupportState] = []
    for target in target_settings.targets:
        try:
            details = build_target_details(target)
        except ValueError:
            continue
        reason = None
        if details.runtime_state in {"Corrupt", "Unreadable"}:
            if details.runtime_state == "Unreadable":
                reason = "target_unreadable"
            else:
                reason = "target_corrupt"
        targets.append(
            TargetSupportState(
                identifier=details.identifier,
                display_name=details.display_name,
                enabled=details.enabled,
                detected=details.detected,
                readable=details.readable,
                writable=details.writable,
                runtime_state=details.runtime_state,
                reason_code=reason,
            )
        )
    history = service.load_operation_history(limit=5)  # type: ignore[attr-defined]
    recent = tuple(
        SupportOperationSummary(
            operation=record.operation,
            outcome=record.outcome,
            timestamp=record.timestamp.replace(microsecond=0).isoformat(),
            record_id=record.record_id[:12],
        )
        for record in history.records
    )
    notices: list[SupportNotice] = []
    if pending:
        notices.append(
            SupportNotice(
                code="pending_recovery",
                title="Pending recovery",
                explanation="An unfinished push journal requires recovery before writes.",
                suggested_action="Open Recovery and finish the pending transaction.",
            )
        )
    if not config_valid:
        notices.append(
            SupportNotice(
                code="invalid_config",
                title="Invalid configuration",
                explanation="spell-sync.toml failed validation.",
                suggested_action="Fix spell-sync.toml, then run spell-sync config-check.",
            )
        )
    return SupportReport(
        schema_version=1,
        generated_at=datetime.now(timezone.utc),
        spell_sync_version=installed_package_version(),
        python_version=sys.version.split()[0],
        operating_system=platform.platform(aliased=True),
        architecture=platform.machine(),
        installation=InstallationInfo(
            package_version=installed_package_version(),
            installation_type="wheel-or-editable",
        ),
        project=ProjectSupportState(
            config_valid=config_valid,
            wordlist_count=word_count,
            pending_recovery=pending,
        ),
        targets=tuple(targets),
        recovery=RecoverySupportState(
            pending_recovery=pending,
            journal_status=journal.status.value,
        ),
        recent_operations=recent,
        notices=tuple(notices),
        privacy=PrivacyManifest(),
    )


def support_report_to_dict(report: SupportReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["generated_at"] = report.generated_at.replace(microsecond=0).isoformat()
    return payload


def format_support_report_text(report: SupportReport) -> str:
    wordlist_count = (
        report.project.wordlist_count if report.project.wordlist_count is not None else "unknown"
    )
    lines = [
        "Spell Sync support report",
        "",
        f"Version: {report.spell_sync_version}",
        f"Generated: {report.generated_at.replace(microsecond=0).isoformat()}",
        f"Python: {report.python_version}",
        f"OS: {report.operating_system}",
        "",
        "Project",
        f"  Config valid: {'Yes' if report.project.config_valid else 'No'}",
        f"  Wordlist count: {wordlist_count}",
        f"  Pending recovery: {'Yes' if report.project.pending_recovery else 'No'}",
        "",
        "Targets",
    ]
    for target in report.targets:
        lines.append(
            f"  {target.display_name}: {target.runtime_state} "
            f"(enabled={target.enabled}, readable={target.readable}, writable={target.writable})"
        )
    if report.notices:
        lines.extend(["", "Notices"])
        for notice in report.notices:
            lines.append(f"  {notice.title}: {notice.explanation}")
    lines.extend(
        [
            "",
            "Privacy",
            "  No words, dictionary contents, or config contents are included.",
            "  Paths and profile names are redacted.",
        ]
    )
    return "\n".join(lines)


def default_support_report_path(state_root: Path | None = None, *, fmt: str = "json") -> Path:
    root = resolve_app_state_paths(state_root=state_root).state_directory / "support-reports"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extension = "json" if fmt == "json" else "txt"
    candidate = root / f"support-report-{stamp}.{extension}"
    counter = 1
    while candidate.exists():
        candidate = root / f"support-report-{stamp}-{counter}.{extension}"
        counter += 1
    return candidate


def export_support_report(
    report: SupportReport,
    *,
    output_path: Path,
    fmt: str,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(f"Report already exists: {output_path}")
    if fmt == "json":
        body = json.dumps(support_report_to_dict(report), indent=2, sort_keys=True) + "\n"
    elif fmt == "text":
        body = format_support_report_text(report) + "\n"
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    temp = output_path.with_suffix(output_path.suffix + ".tmp")
    temp.write_text(body, encoding="utf-8")
    temp.replace(output_path)
    return output_path


def sanitize_support_payload(text: str) -> str:
    return redact_text(text)
