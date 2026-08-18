"""Diagnostic path security and symlink handling tests."""

from datetime import UTC, datetime
from pathlib import Path

from spell_sync.application.reports import OperationOutcome
from spell_sync.application.service import SpellSyncService
from spell_sync.diagnostics.history_record import OperationHistoryRecord
from spell_sync.diagnostics.history_store import OperationHistoryStore
from spell_sync.diagnostics.path_guard import (
    open_append_only,
    validate_directory_path,
    validate_file_path,
)
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.technical_logging import (
    configure_file_logging,
    read_technical_log_tail,
    reset_logging_for_tests,
)
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
from spell_sync.project_setup.prepare import prepare_project_setup


def _paths(tmp_path: Path):
    return resolve_app_state_paths(state_root=tmp_path / "state")


def _record(record_id: str = "sec-1") -> OperationHistoryRecord:
    return OperationHistoryRecord(
        schema_version=1,
        record_id=record_id,
        timestamp=datetime(2026, 7, 19, tzinfo=UTC),
        operation="push",
        outcome="completed",
        duration_ms=1,
    )


def test_history_rejects_symlink_target(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("", encoding="utf-8")
    paths.history_file.symlink_to(outside)
    store = OperationHistoryStore(paths)
    result = store.append(_record())
    assert not result.ok
    assert outside.read_text(encoding="utf-8") == ""


def test_history_clear_does_not_remove_external_symlink_target(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"schema_version":1}\n', encoding="utf-8")
    paths.history_file.symlink_to(outside)
    store = OperationHistoryStore(paths)
    result = store.clear()
    assert not result.ok
    assert outside.is_file()


def test_technical_log_rejects_symlink(tmp_path: Path, monkeypatch) -> None:
    reset_logging_for_tests()
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.log"
    outside.write_text("secret\n", encoding="utf-8")
    paths.technical_log.symlink_to(outside)
    result = configure_file_logging(paths)
    assert not result.ok


def test_history_append_failure_does_not_change_setup_outcome(tmp_path: Path, monkeypatch) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    draft = SetupDraft(tmp_path / "wordlist.txt", ("chrome",), create_wordlist=True)
    prepared = prepare_project_setup(draft)
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message="ok",
        created_files=("wordlist.txt",),
    )
    store = service._history_store

    def blocked_append(_record):
        from spell_sync.diagnostics.types import HistoryWriteResult

        return HistoryWriteResult(ok=False, detail="unsafe path")

    monkeypatch.setattr(store, "append", blocked_append)
    report = service.build_setup_report(execution)
    assert report.outcome == OperationOutcome.COMPLETED
    assert any("history record could not be saved" in warning for warning in report.warnings)


def test_logging_reconfigures_for_new_state_root(tmp_path: Path) -> None:
    reset_logging_for_tests()
    first = _paths(tmp_path / "first")
    second = _paths(tmp_path / "second")
    first.state_directory.mkdir(parents=True)
    second.state_directory.mkdir(parents=True)
    assert configure_file_logging(first).ok
    from spell_sync.diagnostics.technical_logging import get_spell_sync_logger

    get_spell_sync_logger().info("first-root")
    assert first.technical_log.is_file()
    assert configure_file_logging(second).ok
    get_spell_sync_logger().info("second-root")
    assert second.technical_log.is_file()
    assert "second-root" in second.technical_log.read_text(encoding="utf-8")
    assert "second-root" not in first.technical_log.read_text(encoding="utf-8")


def test_future_schema_version_is_skipped(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    paths.history_file.write_text(
        '{"schema_version": 99, "record_id": "x", "timestamp": "2026-07-19T00:00:00+00:00", '
        '"operation": "push", "outcome": "completed", "duration_ms": 1}\n',
        encoding="utf-8",
    )
    store = OperationHistoryStore(paths)
    read = store.read_recent(limit=10)
    assert read.records == ()
    assert read.malformed_lines == 1


def test_path_guard_rejects_directory_as_file_target(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    blocker = root / "blocked"
    blocker.write_text("not-a-dir", encoding="utf-8")
    result = validate_directory_path(blocker, root=root)
    assert not result.ok


def test_path_guard_rejects_symlink_directory(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "linked"
    link.symlink_to(outside)
    result = validate_directory_path(link, root=root)
    assert not result.ok


def test_path_guard_rejects_directory_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    result = validate_directory_path(outside, root=root)
    assert not result.ok


def test_path_guard_rejects_file_as_directory(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    target = root / "history.jsonl"
    target.mkdir()
    result = validate_file_path(target, root=root)
    assert not result.ok


def test_path_guard_rejects_parent_that_is_file(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    parent_file = root / "parent-file"
    parent_file.write_text("x", encoding="utf-8")
    nested = parent_file / "child.jsonl"
    result = validate_file_path(nested, root=root)
    assert not result.ok


def test_path_guard_rejects_symlink_file(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("secret", encoding="utf-8")
    link = root / "spell-sync.log"
    link.symlink_to(outside)
    result = validate_file_path(link, root=root)
    assert not result.ok


def test_path_guard_rejects_file_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("secret", encoding="utf-8")
    result = validate_file_path(outside, root=root)
    assert not result.ok


def test_path_guard_rejects_symlink_parent(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = root / "linked"
    linked_parent.symlink_to(outside)
    target = linked_parent / "history.jsonl"
    result = validate_file_path(target, root=root)
    assert not result.ok


def test_open_append_only_reports_mkdir_failure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "state"
    root.mkdir()
    target = root / "nested" / "history.jsonl"

    def fail_mkdir(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    fd, detail = open_append_only(target, root=root)
    assert fd is None
    assert detail == "unwritable"


def test_open_append_only_reports_open_failure(tmp_path: Path, monkeypatch) -> None:
    import os

    root = tmp_path / "state"
    root.mkdir()
    target = root / "history.jsonl"

    def fail_open(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(os, "open", fail_open)
    fd, detail = open_append_only(target, root=root)
    assert fd is None
    assert detail == "unwritable"


def test_read_technical_log_rejects_symlink(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.log"
    outside.write_text("secret\n", encoding="utf-8")
    paths.technical_log.symlink_to(outside)
    snapshot = read_technical_log_tail(paths)
    assert snapshot.detail is not None
    assert snapshot.lines == ()


def test_history_lock_path_is_symlink(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.lock"
    outside.write_text("", encoding="utf-8")
    paths.history_lock.symlink_to(outside)
    store = OperationHistoryStore(paths)
    result = store.append(_record("lock-symlink"))
    assert not result.ok


def test_history_state_directory_symlink_blocks_append(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "state-link"
    link.symlink_to(real)
    from spell_sync.diagnostics.paths import AppStatePaths

    paths = AppStatePaths(
        state_directory=link,
        history_file=link / "operation-history.jsonl",
        history_lock=link / "operation-history.lock",
        technical_log=link / "spell-sync.log",
        log_root=link,
    )
    store = OperationHistoryStore(paths)
    result = store.append(_record("symlink-state"))
    assert not result.ok


def test_path_guard_rejects_parent_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "history.jsonl"
    result = validate_file_path(target, root=root)
    assert not result.ok


def test_open_append_only_reports_directory_check_failure(tmp_path: Path, monkeypatch) -> None:
    from spell_sync.diagnostics.path_guard import PathCheckResult

    root = tmp_path / "state"
    root.mkdir()
    target = root / "history.jsonl"

    monkeypatch.setattr(
        "spell_sync.diagnostics.path_guard.validate_directory_path",
        lambda *args, **kwargs: PathCheckResult(False, "bad directory"),
    )
    fd, detail = open_append_only(target, root=root)
    assert fd is None
    assert detail == "bad directory"


def test_history_read_rejects_symlink_file(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_text(
        '{"schema_version": 1, "record_id": "x", "timestamp": "2026-07-19T00:00:00+00:00", '
        '"operation": "push", "outcome": "completed", "duration_ms": 1}\n',
        encoding="utf-8",
    )
    paths.history_file.symlink_to(outside)
    store = OperationHistoryStore(paths)
    read = store.read_recent(limit=10)
    assert read.records == ()
    assert read.detail is not None
