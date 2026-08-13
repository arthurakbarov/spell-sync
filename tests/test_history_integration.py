"""Integration tests: one history record per completed operation."""

import json
from pathlib import Path

from spell_sync.application.reports import (
    OperationOutcome,
    PullExecution,
    PullPreview,
    PushExecution,
    RecoveryExecution,
    RecoveryOutcome,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.diagnostics.history_store import OperationHistoryStore
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.types import HistoryWriteResult
from spell_sync.exit_codes import ExitCode
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
from spell_sync.project_setup.prepare import prepare_project_setup


def _paths(tmp_path: Path):
    return resolve_app_state_paths(state_root=tmp_path / "state")


def _records(tmp_path: Path):
    store = OperationHistoryStore(_paths(tmp_path))
    return store.read_recent(limit=20).records


def test_setup_success_creates_history_record(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    prepared = prepare_project_setup(
        SetupDraft(tmp_path / "wordlist.txt", ("chrome",), create_wordlist=True)
    )
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message="ok",
        created_files=("wordlist.txt", "spell-sync.toml"),
    )
    service.build_setup_report(execution)
    records = _records(tmp_path)
    assert len(records) == 1
    assert records[0].operation == "setup"
    assert records[0].outcome == "completed"
    assert records[0].created_files == 2


def test_push_success_creates_history_record(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    preview = PullPreview(
        wordlist_path=str(tmp_path / "wordlist.txt"),
        additions=2,
        before_count=1,
        after_count=3,
        sources_used=("chrome",),
        sources_skipped=(),
        source_rows=(),
        warnings=(),
        created_at="2026-07-18T00:00:00+00:00",
        plan_identifier="pull-plan",
        merged_words=("a", "b", "c"),
    )
    execution = PullExecution(
        preview=preview,
        result=(1, 3),
        outcome=OperationOutcome.COMPLETED,
        message="ok",
    )
    service.build_pull_report(execution)
    records = _records(tmp_path)
    assert len(records) == 1
    assert records[0].operation == "pull"
    assert records[0].added_words == 2


def test_duplicate_report_build_does_not_duplicate_record(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    prepared = prepare_project_setup(
        SetupDraft(tmp_path / "wordlist.txt", (), create_wordlist=True)
    )
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message="ok",
        created_files=("wordlist.txt",),
    )
    service.build_setup_report(execution)
    service.build_setup_report(execution)
    assert len(_records(tmp_path)) == 1


def test_history_failure_adds_warning_not_outcome_change(tmp_path: Path, monkeypatch) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    prepared = prepare_project_setup(
        SetupDraft(tmp_path / "wordlist.txt", ("chrome",), create_wordlist=True)
    )
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message="ok",
        created_files=("wordlist.txt",),
    )
    monkeypatch.setattr(
        service._history_store,
        "append",
        lambda _record: HistoryWriteResult(ok=False, detail="disk full"),
    )
    report = service.build_setup_report(execution)
    assert report.outcome == OperationOutcome.COMPLETED
    assert any("history record could not be saved" in warning for warning in report.warnings)
    assert len(_records(tmp_path)) == 0


def test_push_stopped_safely_history_outcome(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    execution = PushExecution(
        prepared=None,
        result=ExitCode.PUSH_ABORT,
        outcome=OperationOutcome.STOPPED_SAFELY,
        message="conflict",
        plan_identifier="plan-x",
    )
    service.build_push_report(execution)
    record = _records(tmp_path)[0]
    assert record.operation == "push"
    assert record.outcome == "stopped_safely"


def test_recovery_cleanup_history_outcome(tmp_path: Path) -> None:
    from tests.tui.fake_service import sample_recovery_preview

    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    preview = sample_recovery_preview()
    execution = RecoveryExecution(
        preview=preview,
        result=ExitCode.OK,
        outcome=RecoveryOutcome.CLEANUP_COMPLETED,
        message="cleanup done",
    )
    service.build_recovery_report(execution)
    record = _records(tmp_path)[0]
    assert record.outcome == "cleanup_completed"


def test_record_json_has_no_word_payload(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    prepared = prepare_project_setup(
        SetupDraft(tmp_path / "wordlist.txt", ("chrome",), create_wordlist=True)
    )
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message="added alpha beta gamma",
        created_files=("wordlist.txt",),
    )
    service.build_setup_report(execution)
    payload = json.dumps(_records(tmp_path)[0].to_json_dict())
    assert "alpha" not in payload
    assert "beta" not in payload
    assert "wordlist.txt" not in payload
