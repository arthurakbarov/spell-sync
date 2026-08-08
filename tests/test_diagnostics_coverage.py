"""Additional coverage for diagnostics modules."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.application.service import SpellSyncService
from spell_sync.diagnostics.history_builder import build_history_record
from spell_sync.diagnostics.history_record import OperationHistoryRecord
from spell_sync.diagnostics.history_store import OperationHistoryStore
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.safe_log import (
    _sanitize_formatted_output,
    safe_repr,
    sanitize_exception_message,
)
from spell_sync.diagnostics.technical_logging import (
    configure_file_logging,
    read_technical_log_tail,
    reset_logging_for_tests,
)


def _paths(tmp_path: Path):
    return resolve_app_state_paths(state_root=tmp_path / "state")


def test_resolve_platform_paths_macos(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_macos", lambda: True)
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_windows", lambda: False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.home_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "spell_sync.diagnostics.paths.app_support_dir",
        lambda: tmp_path / "AppSupport",
    )
    paths = resolve_app_state_paths()
    assert "Logs" in str(paths.technical_log)


def test_resolve_platform_paths_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_macos", lambda: False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    paths = resolve_app_state_paths()
    assert paths.state_directory.name == "spell-sync"


def test_resolve_platform_paths_linux_xdg(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_macos", lambda: False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_windows", lambda: False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    paths = resolve_app_state_paths()
    assert paths.state_directory.parent.name == "xdg"


def test_history_append_oserror(tmp_path: Path, monkeypatch) -> None:
    store = OperationHistoryStore(_paths(tmp_path))

    monkeypatch.setattr(
        "spell_sync.diagnostics.history_store.open_append_only",
        lambda *args, **kwargs: (None, "disk full"),
    )
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="x",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert not result.ok


def test_history_read_oserror(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    paths.history_file.write_text("{}\n", encoding="utf-8")
    store = OperationHistoryStore(paths)

    def fail_read_text(self, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    result = store.read_recent(limit=5)
    assert result.records == ()
    assert result.detail


def test_history_lock_unavailable(tmp_path: Path, monkeypatch) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    monkeypatch.setattr(
        "spell_sync.diagnostics.history_store._try_acquire_fd",
        lambda *_args, **_kwargs: False,
    )
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="lock",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert not result.ok


def test_compaction_write_failure(tmp_path: Path, monkeypatch, history_record_cap: int) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    for index in range(history_record_cap + 2):
        store.append(
            OperationHistoryRecord(
                schema_version=1,
                record_id=f"c-{index}",
                timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                operation="push",
                outcome="completed",
                duration_ms=1,
            )
        )

    original_replace = Path.replace

    def fail_replace(self, target):
        if str(self).endswith(".jsonl.tmp"):
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="trigger-compact",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert result.ok


def test_history_record_optional_fields() -> None:
    record = OperationHistoryRecord(
        schema_version=1,
        record_id="full",
        timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc),
        operation="recover",
        outcome="completed",
        duration_ms=1,
        transaction_id="tx",
        setup_id="setup",
        restored_files=1,
        removed_created_files=1,
        conflicts=1,
        created_files=1,
        enabled_targets=1,
        added_words=1,
        sources_used=1,
        sources_skipped=1,
    )
    payload = record.to_json_dict()
    assert payload["transaction_id"] == "tx"
    assert payload["setup_id"] == "setup"
    assert OperationHistoryRecord.from_json_dict({"schema_version": 1, "bad": True}) is None


def test_setup_history_builder_branches() -> None:
    from spell_sync.project_setup.draft import SetupDraft
    from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
    from spell_sync.project_setup.prepare import prepare_project_setup

    prepared = prepare_project_setup(SetupDraft(Path("/tmp/w.txt"), (), create_wordlist=True))
    stopped = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.STOPPED_SAFELY,
        message="stopped",
    )
    report = OperationReport(
        operation="setup",
        outcome=OperationOutcome.STOPPED_SAFELY,
        title="t",
        summary="s",
        plan_identifier=prepared.setup_id,
    )
    record = build_history_record(report, source=stopped)
    assert record.outcome == "stopped_safely"


def test_safe_log_helpers() -> None:
    assert sanitize_exception_message(None) is None
    assert safe_repr({"secret": "word"}) == "dict"
    formatted = _sanitize_formatted_output("RuntimeError: boom secret-token\nnext")
    assert "secret-token" not in formatted


def test_configure_file_logging_failure(tmp_path: Path, monkeypatch) -> None:
    reset_logging_for_tests()
    paths = _paths(tmp_path)

    def fail_mkdir(*args, **kwargs):
        raise OSError("no permission")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    result = configure_file_logging(paths)
    assert not result.ok


def test_read_technical_log_read_failure(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    paths.technical_log.parent.mkdir(parents=True)
    paths.technical_log.write_text("hello\n", encoding="utf-8")

    def fail_read_bytes(self, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    snapshot = read_technical_log_tail(paths)
    assert snapshot.detail


def test_read_technical_log_line_limit(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.technical_log.parent.mkdir(parents=True)
    payload = "\n".join(f"line-{index}" for index in range(300))
    paths.technical_log.write_text(payload, encoding="utf-8")
    snapshot = read_technical_log_tail(paths, max_lines=50)
    assert len(snapshot.lines) <= 50
    assert snapshot.truncated


def test_history_outcome_filter_and_empty_lines(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="a",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    paths = store.paths
    paths.history_file.write_text(
        paths.history_file.read_text(encoding="utf-8") + "\n\n[]\n",
        encoding="utf-8",
    )
    filtered = store.read_recent(limit=10, outcome=OperationOutcome.FAILED)
    assert filtered.records == ()


def test_history_clear_lock_unavailable(tmp_path: Path, monkeypatch) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="clear",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    monkeypatch.setattr(
        "spell_sync.diagnostics.history_store._try_acquire_fd",
        lambda *_args, **_kwargs: False,
    )
    assert not store.clear().ok


def test_pull_execution_failed_branch() -> None:
    from spell_sync.application.reports import PullPreview
    from spell_sync.application.service import SpellSyncService
    from spell_sync.exit_codes import ExitCode

    preview = PullPreview(
        wordlist_path="/tmp/w.txt",
        additions=0,
        before_count=0,
        after_count=0,
        sources_used=(),
        sources_skipped=(),
        source_rows=(),
        warnings=(),
        created_at="2026-01-01T00:00:00+00:00",
        plan_identifier="plan",
        merged_words=(),
    )
    service = SpellSyncService(enable_file_logging=False)
    execution = service.pull_execution_from_result(preview, ExitCode.PUSH_ABORT)
    assert execution.outcome.value == "failed"


def test_service_log_setup_warning(tmp_path: Path, monkeypatch) -> None:
    reset_logging_for_tests()
    from spell_sync.diagnostics.types import LoggingSetupResult

    monkeypatch.setattr(
        "spell_sync.application.service.configure_file_logging",
        lambda _paths: LoggingSetupResult(ok=False, detail="nope"),
    )
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=True)
    assert service is not None


def test_lazy_spell_sync_service_export() -> None:
    import spell_sync.application as application

    assert application.SpellSyncService is not None


def test_setup_incomplete_history_record() -> None:
    from spell_sync.project_setup.draft import SetupDraft
    from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
    from spell_sync.project_setup.prepare import prepare_project_setup

    prepared = prepare_project_setup(SetupDraft(Path("/tmp/w.txt"), (), create_wordlist=True))
    execution = ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.SETUP_INCOMPLETE,
        message="partial",
    )
    report = OperationReport(
        operation="setup",
        outcome=OperationOutcome.FAILED,
        title="t",
        summary="s",
        plan_identifier=prepared.setup_id,
    )
    record = build_history_record(report, source=execution)
    assert record.outcome == "setup_incomplete"


def test_target_written_status_count() -> None:
    from spell_sync.application.reports import TargetUpdateReport

    report = OperationReport(
        operation="push",
        outcome=OperationOutcome.COMPLETED,
        title="Push",
        summary="ok",
        target_updates=(TargetUpdateReport("a", 1, 0, "written"),),
    )
    record = build_history_record(report)
    assert record.updated_targets == 1


def test_linux_default_state_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_macos", lambda: False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.is_windows", lambda: False)
    monkeypatch.setattr("spell_sync.diagnostics.paths.home_dir", lambda: tmp_path)
    paths = resolve_app_state_paths()
    assert ".local" in str(paths.state_directory)


def test_sanitize_forbidden_substring() -> None:
    from spell_sync.diagnostics.safe_log import sanitize_log_message

    assert sanitize_log_message("removed words: [x]") == "[redacted diagnostic message]"
    assert sanitize_exception_message("plain failure") == "[sanitized exception message]"
    assert sanitize_exception_message("token=abc") == "[sanitized exception message]"


def test_history_duplicate_check_read_failure(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    paths.state_directory.mkdir(parents=True)
    paths.history_file.write_text('{"schema_version":1}\n', encoding="utf-8")
    store = OperationHistoryStore(paths)

    def fail_read_text(self, *args, **kwargs):
        if str(self).endswith("operation-history.jsonl"):
            raise OSError("denied")
        return Path.read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="retry",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert result.ok


def test_compaction_read_failure(tmp_path: Path, monkeypatch, history_record_cap: int) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    for index in range(history_record_cap + 1):
        store.append(
            OperationHistoryRecord(
                schema_version=1,
                record_id=f"compact-{index}",
                timestamp=datetime.now(timezone.utc),
                operation="push",
                outcome="completed",
                duration_ms=1,
            )
        )
    original = Path.read_text

    def fail_on_compact(self, *args, **kwargs):
        if str(self).endswith("operation-history.jsonl"):
            raise OSError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_on_compact)
    store._maybe_compact_unlocked()
    assert store.paths.history_file.is_file()


def test_compaction_temp_unlink_failure(
    tmp_path: Path, monkeypatch, history_record_cap: int
) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    for index in range(history_record_cap + 2):
        store.append(
            OperationHistoryRecord(
                schema_version=1,
                record_id=f"tmp-{index}",
                timestamp=datetime.now(timezone.utc),
                operation="push",
                outcome="completed",
                duration_ms=1,
            )
        )

    def fail_replace(self, target):
        raise OSError("replace failed")

    def fail_unlink(self):
        raise OSError("unlink failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="trigger-temp-fail",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert result.ok


def test_read_technical_log_byte_truncation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.technical_log.parent.mkdir(parents=True)
    paths.technical_log.write_bytes(b"x" * (200 * 1024))
    snapshot = read_technical_log_tail(paths, max_bytes=1024, max_lines=500)
    assert snapshot.truncated


def test_service_state_paths_and_clear(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=False)
    assert service.state_paths.history_file.name == "operation-history.jsonl"
    assert service.clear_operation_history().ok


def test_application_getattr_unknown() -> None:
    import spell_sync.application as application

    with pytest.raises(AttributeError):
        _ = application.not_a_real_export


def test_compaction_missing_history_file(tmp_path: Path) -> None:
    store = OperationHistoryStore(_paths(tmp_path))
    assert store.paths.history_file.is_file() is False
    store._maybe_compact_unlocked()


def test_nonblocking_lock_contended(monkeypatch) -> None:
    import fcntl

    from spell_sync.diagnostics.history_store import _release_fd, _try_acquire_fd

    def fail_flock(_fd, _flags):
        raise BlockingIOError()

    monkeypatch.setattr(fcntl, "flock", fail_flock)
    assert _try_acquire_fd(0, blocking=False) is False
    _release_fd(0)


def test_lock_close_failure(tmp_path: Path, monkeypatch) -> None:
    import os

    store = OperationHistoryStore(_paths(tmp_path))

    def fail_close(_fd):
        raise OSError("close failed")

    monkeypatch.setattr(os, "close", fail_close)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="close-fail",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert result.ok


def test_history_record_clamps_negative_and_overflow_counts() -> None:
    record = OperationHistoryRecord.from_json_dict(
        {
            "schema_version": 1,
            "record_id": "clamp",
            "timestamp": "2026-07-19T00:00:00",
            "operation": "push",
            "outcome": "completed",
            "duration_ms": 1,
            "updated_targets": -5,
            "additions": 20_000_000,
        }
    )
    assert record is not None
    assert record.updated_targets == 0
    assert record.additions == 10_000_000


def test_history_append_write_failure(tmp_path: Path, monkeypatch) -> None:
    import os

    store = OperationHistoryStore(_paths(tmp_path))

    def fail_write(*args, **kwargs):
        raise OSError("write failed")

    monkeypatch.setattr(os, "write", fail_write)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="write-fail",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert not result.ok


def test_history_state_dir_creation_failure(tmp_path: Path, monkeypatch) -> None:
    store = OperationHistoryStore(_paths(tmp_path))

    def fail_mkdir(*args, **kwargs):
        raise OSError("mkdir failed")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    result = store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="mkdir-fail",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert not result.ok


def test_compaction_temp_path_symlink(tmp_path: Path, history_record_cap: int) -> None:
    paths = _paths(tmp_path)
    store = OperationHistoryStore(paths)
    for index in range(history_record_cap):
        store.append(
            OperationHistoryRecord(
                schema_version=1,
                record_id=f"tmp-{index}",
                timestamp=datetime.now(timezone.utc),
                operation="push",
                outcome="completed",
                duration_ms=1,
            )
        )
    outside = tmp_path / "outside.tmp"
    outside.write_text("blocked", encoding="utf-8")
    temp_path = paths.history_file.with_suffix(".jsonl.tmp")
    temp_path.symlink_to(outside)
    store.append(
        OperationHistoryRecord(
            schema_version=1,
            record_id="tmp-trigger",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
        )
    )
    assert outside.read_text(encoding="utf-8") == "blocked"


def test_compaction_cleanup_unlink_failure(
    tmp_path: Path, monkeypatch, history_record_cap: int
) -> None:
    paths = _paths(tmp_path)
    store = OperationHistoryStore(paths)
    for index in range(history_record_cap + 1):
        store.append(
            OperationHistoryRecord(
                schema_version=1,
                record_id=f"cleanup-{index}",
                timestamp=datetime.now(timezone.utc),
                operation="push",
                outcome="completed",
                duration_ms=1,
            )
        )

    def fail_replace(self, target):
        raise OSError("replace failed")

    def fail_unlink(self):
        raise OSError("unlink failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    store._maybe_compact_unlocked()
    assert paths.history_file.is_file()


def test_logging_rejects_symlink_log_directory(tmp_path: Path) -> None:
    reset_logging_for_tests()
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    log_parent = root / "logs"
    log_parent.symlink_to(outside)
    from spell_sync.diagnostics.paths import AppStatePaths

    paths = AppStatePaths(
        state_directory=root,
        history_file=root / "operation-history.jsonl",
        history_lock=root / "operation-history.lock",
        technical_log=log_parent / "spell-sync.log",
        log_root=root,
    )
    result = configure_file_logging(paths)
    assert not result.ok


def test_format_safe_log_record_with_reason_code() -> None:
    import logging

    from spell_sync.diagnostics.safe_log import format_safe_log_record

    record = logging.LogRecord(
        name="spell_sync",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed",
        args=(),
        exc_info=None,
    )
    record.reason_code = "push_blocked"
    try:
        raise RuntimeError("token=secret")
    except RuntimeError:
        record.exc_info = sys.exc_info()
    formatted = format_safe_log_record(record, "ERROR spell_sync failed")
    assert "reason_code=push_blocked" in formatted
    assert "secret" not in formatted


def test_sanitize_formatted_output_redacts_traceback_lines() -> None:
    from spell_sync.diagnostics.safe_log import _sanitize_formatted_output

    text = "ERROR boom\n  File /Users/me/secret.py\nValueError: token=abc"
    cleaned = _sanitize_formatted_output(text)
    assert "/Users/me" not in cleaned
    assert "abc" not in cleaned
    assert "File [redacted]" in cleaned
