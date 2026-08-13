"""Operation history store tests."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from spell_sync.application.events import OperationKind
from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.application.service import SpellSyncService
from spell_sync.diagnostics.history_builder import build_history_record
from spell_sync.diagnostics.history_record import OperationHistoryRecord
from spell_sync.diagnostics.history_store import OperationHistoryStore
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.safe_log import sanitize_log_message
from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome


def _record(
    *,
    record_id: str = "abc",
    operation: str = "push",
    outcome: str = "completed",
) -> OperationHistoryRecord:
    return OperationHistoryRecord(
        schema_version=1,
        record_id=record_id,
        timestamp=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        operation=operation,
        outcome=outcome,
        duration_ms=10,
        updated_targets=2,
    )


def _paths(tmp_path: Path):
    return resolve_app_state_paths(state_root=tmp_path / "state")


def test_append_and_read_newest_first(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    first = _record(record_id="one")
    second = _record(record_id="two", operation="pull")
    assert store.append(first).ok
    assert store.append(second).ok
    result = store.read_recent(limit=10)
    assert [item.record_id for item in result.records] == ["two", "one"]


def test_duplicate_record_prevention(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    record = _record(record_id="dup")
    assert store.append(record).ok
    again = store.append(record)
    assert again.ok and again.duplicate
    assert len(store.read_recent(limit=10).records) == 1


def test_malformed_line_is_skipped(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    paths.history_file.write_text(
        "{bad json\n" + json.dumps(_record().to_json_dict()) + "\n", encoding="utf-8"
    )
    store = OperationHistoryStore(paths)
    read = store.read_recent(limit=10)
    assert len(read.records) == 1
    assert read.malformed_lines == 1


def test_compaction_keeps_newest(tmp_path: Path, history_record_cap: int) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    for index in range(history_record_cap + 5):
        store.append(_record(record_id=f"id-{index:03d}"))
    records = store.read_recent(limit=history_record_cap + 10).records
    assert len(records) <= history_record_cap
    assert records[0].record_id == f"id-{history_record_cap + 4:03d}"


def test_clear_history(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    store.append(_record())
    assert store.clear().ok
    assert store.read_recent(limit=10).records == ()


def test_history_failure_does_not_change_operation_outcome(tmp_path: Path, monkeypatch) -> None:
    from spell_sync.diagnostics.types import HistoryWriteResult
    from spell_sync.project_setup.draft import SetupDraft
    from spell_sync.project_setup.prepare import prepare_project_setup

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
        lambda _record: HistoryWriteResult(ok=False, detail="fail"),
    )
    report = service.build_setup_report(execution)
    assert report.outcome.value == "completed"
    assert any("history record could not be saved" in warning for warning in report.warnings)


def test_build_history_record_from_report() -> None:
    report = OperationReport(
        operation="push",
        outcome=OperationOutcome.COMPLETED,
        title="Update my apps completed",
        summary="ok",
        plan_identifier="plan-1",
    )
    record = build_history_record(report)
    assert record.operation == "push"
    assert record.transaction_id == "plan-1"
    assert "alpha" not in json.dumps(record.to_json_dict())


def test_redaction_removes_secrets() -> None:
    cleaned = sanitize_log_message("token=super-secret-value removed words: [bad]")
    assert "super-secret" not in cleaned
    assert "removed words" not in cleaned.lower()


def test_concurrent_append(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))

    def worker(index: int) -> None:
        store.append(_record(record_id=f"thread-{index}"))

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(store.read_recent(limit=50).records) == 20


def test_service_filters(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    store.append(_record(record_id="push-1", operation="push"))
    store.append(_record(record_id="pull-1", operation="pull", outcome="completed"))
    service = SpellSyncService(
        state_paths=_paths(tmp_path), history_store=store, enable_file_logging=False
    )
    snapshot = service.load_operation_history(limit=10, operation=OperationKind.PULL)
    assert len(snapshot.records) == 1
    assert snapshot.records[0].operation == "pull"


def test_truncated_and_unsupported_schema_lines(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    paths.history_file.write_text(
        '{"schema_version": 99, "record_id": "x"}\n'
        + json.dumps(_record(record_id="ok").to_json_dict())
        + "\n",
        encoding="utf-8",
    )
    store = OperationHistoryStore(paths)
    read = store.read_recent(limit=10)
    assert len(read.records) == 1
    assert read.malformed_lines == 1


def test_clear_failure(tmp_path: Path, monkeypatch) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    store.append(_record())
    paths = store.paths

    def fail_unlink(_self):
        raise OSError("permission denied")

    monkeypatch.setattr(type(paths.history_file), "unlink", fail_unlink)
    result = store.clear()
    assert not result.ok


def test_read_missing_file(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    assert store.read_recent(limit=5).records == ()


def test_history_builder_target_status_branches() -> None:
    from spell_sync.application.reports import OperationReport, TargetUpdateReport
    from spell_sync.diagnostics.history_builder import build_history_record

    report = OperationReport(
        operation="push",
        outcome=OperationOutcome.COMPLETED,
        title="Push",
        summary="ok",
        target_updates=(
            TargetUpdateReport("a", 1, 0, "unchanged"),
            TargetUpdateReport("b", 0, 0, "skipped"),
            TargetUpdateReport("c", 0, 0, "failed"),
        ),
    )
    record = build_history_record(report)
    assert record.unchanged_targets == 1
    assert record.skipped_targets == 1
    assert record.failed_targets == 1
