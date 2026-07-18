"""Project setup detection, preview, execution, and CLI sharing."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from spell_sync.application import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.commands import cmd_init
from spell_sync.project_setup.discovery import discover_setup_targets
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import (
    ProjectSetupExecution,
    ProjectSetupOutcome,
    execute_project_setup,
)
from spell_sync.project_setup.prepare import SetupFileAction, prepare_project_setup
from spell_sync.project_setup.state import (
    ProjectSetupStatus,
    inspect_project_setup,
    normalize_wordlist_input,
    validate_setup_wordlist,
)
from spell_sync.tui.controller import TuiController
from tests.journal_test_utils import write_test_journal


@pytest.fixture
def service() -> SpellSyncService:
    return SpellSyncService()


def test_setup_ready_project(tmp_path: Path, service: SpellSyncService) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (tmp_path / "spell-sync.toml").write_text("[push]\nstrict = false\n", encoding="utf-8")
    state = service.inspect_project_setup(CliOptions(wordlist=str(wordlist)))
    assert state.status is ProjectSetupStatus.READY
    assert state.can_start_wizard is False


def test_setup_missing_project(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(home)
    monkeypatch.setattr("spell_sync.paths.project_root", lambda: home)
    state = inspect_project_setup(CliOptions())
    assert state.status is ProjectSetupStatus.MISSING_PROJECT
    assert state.can_start_wizard is True


def test_setup_missing_config(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    state = inspect_project_setup(CliOptions(wordlist=str(wordlist)))
    assert state.status is ProjectSetupStatus.MISSING_CONFIG
    assert state.can_start_wizard is False


def test_setup_invalid_config(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (tmp_path / "spell-sync.toml").write_text("not valid toml [[[\n", encoding="utf-8")
    state = inspect_project_setup(CliOptions(wordlist=str(wordlist)))
    assert state.status is ProjectSetupStatus.INVALID_CONFIG
    assert state.can_start_wizard is False


def test_setup_unreadable_wordlist(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    wordlist.chmod(0)
    try:
        state = inspect_project_setup(CliOptions(wordlist=str(wordlist)))
    finally:
        wordlist.chmod(stat.S_IWUSR | stat.S_IRUSR)
    assert state.status is ProjectSetupStatus.UNREADABLE_WORDLIST
    assert state.can_start_wizard is False


def test_setup_recovery_required(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    write_test_journal(wordlist, wordlist_write_started=True)
    state = inspect_project_setup(CliOptions(wordlist=str(wordlist)))
    assert state.status is ProjectSetupStatus.RECOVERY_REQUIRED
    assert state.can_start_wizard is False


def test_wordlist_tilde_expansion(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    path = normalize_wordlist_input("~/spell-words/wordlist.txt")
    assert path == (home / "spell-words" / "wordlist.txt").resolve()


def test_wordlist_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directory"):
        normalize_wordlist_input(str(tmp_path))


def test_wordlist_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="required"):
        normalize_wordlist_input("   ")


def test_wordlist_rejects_parent_file(tmp_path: Path) -> None:
    parent = tmp_path / "parent-file"
    parent.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Parent path"):
        normalize_wordlist_input(str(parent / "wordlist.txt"))


def test_existing_wordlist_validation(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("one\ntwo\n", encoding="utf-8")
    path, detail = validate_setup_wordlist(str(wordlist))
    assert path == wordlist.resolve()
    assert detail is not None
    assert "2 words" in detail


def test_new_wordlist_validation(tmp_path: Path) -> None:
    wordlist = tmp_path / "new" / "wordlist.txt"
    _, detail = validate_setup_wordlist(str(wordlist))
    assert detail is not None
    assert "will be created" in detail


def test_target_discovery_read_only(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    before = {p for p in home.rglob("*")}
    discovery = discover_setup_targets()
    after = {p for p in home.rglob("*")}
    assert before == after
    assert discovery.targets


def test_prepare_creates_plan_for_new_project(tmp_path: Path) -> None:
    wordlist = tmp_path / "project" / "wordlist.txt"
    discovery = discover_setup_targets()
    draft = SetupDraft(
        wordlist_path=wordlist,
        selected_targets=discovery.default_enabled,
        create_wordlist=True,
    )
    prepared = prepare_project_setup(draft)
    assert prepared.can_execute is True
    create_names = {
        item.relative_name for item in prepared.files if item.action is SetupFileAction.CREATE
    }
    assert "wordlist.txt" in create_names
    assert "spell-sync.toml" in create_names


def test_prepare_keeps_existing_wordlist(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    original = b"keep\nme\n"
    wordlist.write_bytes(original)
    draft = SetupDraft(wordlist, (), create_wordlist=False)
    prepared = prepare_project_setup(draft)
    keep = next(item for item in prepared.files if item.relative_name == "wordlist.txt")
    assert keep.action is SetupFileAction.KEEP
    assert prepared.existing_wordlist_kept is True


def test_execute_new_project_success(tmp_path: Path) -> None:
    wordlist = tmp_path / "project" / "wordlist.txt"
    draft = SetupDraft(wordlist, ("chrome",), create_wordlist=True)
    prepared = prepare_project_setup(draft)
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.COMPLETED
    assert wordlist.is_file()
    assert (wordlist.parent / "spell-sync.toml").is_file()


def test_execute_preserves_existing_wordlist_bytes(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    original = b"alpha\nbeta\n"
    wordlist.write_bytes(original)
    draft = SetupDraft(wordlist, ("chrome",), create_wordlist=False)
    prepared = prepare_project_setup(draft)
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.COMPLETED
    assert wordlist.read_bytes() == original


def test_execute_conflict_when_config_appears(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    draft = SetupDraft(wordlist, (), create_wordlist=True)
    prepared = prepare_project_setup(draft)
    (wordlist.parent / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.STOPPED_SAFELY
    assert "appeared" in execution.message.lower() or "conflict" in execution.message.lower()


def test_execute_stale_setup_id_rejected(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id="wrong-id",
    )
    assert execution.outcome is ProjectSetupOutcome.FAILED


def test_cli_init_uses_service_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with patch.object(SpellSyncService, "prepare_project_setup") as prepare:
        with patch.object(SpellSyncService, "execute_project_setup") as execute:
            prepared = prepare.return_value = prepare_project_setup(
                SetupDraft(tmp_path / "wordlist.txt", (), create_wordlist=True)
            )
            execute.return_value = execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
            )
            code = cmd_init(CliOptions())
    assert code == 0
    prepare.assert_called_once()
    execute.assert_called_once()


def test_cli_and_service_share_execution_entrypoint(tmp_path: Path, monkeypatch) -> None:
    wordlist = tmp_path / "wordlist.txt"
    service = SpellSyncService()
    monkeypatch.chdir(tmp_path)
    with patch.object(
        SpellSyncService,
        "execute_project_setup",
        wraps=service.execute_project_setup,
    ) as execute:
        code = cmd_init(CliOptions(wordlist=str(wordlist)))
    assert code == 0
    assert execute.call_count == 1
    assert wordlist.is_file()
    assert (wordlist.parent / "spell-sync.toml").is_file()


def test_execute_rejects_preview_with_conflicts(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    (tmp_path / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
    prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.STOPPED_SAFELY


def test_execute_setup_incomplete_on_write_failure(tmp_path: Path, monkeypatch) -> None:
    wordlist = tmp_path / "project" / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
    from spell_sync.project_setup import execute as setup_execute

    original = setup_execute.atomic_write
    calls = {"count": 0}

    def flaky_write(path, content, *, keep_backup=False):
        calls["count"] += 1
        if calls["count"] == 1:
            return original(path, content, keep_backup=keep_backup)
        raise OSError("disk full")

    monkeypatch.setattr(
        "spell_sync.project_setup.execute.atomic_write",
        flaky_write,
    )
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome in {
        ProjectSetupOutcome.SETUP_INCOMPLETE,
        ProjectSetupOutcome.FAILED,
    }


def test_setup_missing_wordlist_with_config(tmp_path: Path) -> None:
    config = tmp_path / "spell-sync.toml"
    config.write_text("[push]\n", encoding="utf-8")
    state = inspect_project_setup(CliOptions(wordlist=str(tmp_path / "wordlist.txt")))
    assert state.status is ProjectSetupStatus.MISSING_WORDLIST


def test_execute_operation_lock_blocks_setup(tmp_path: Path, monkeypatch) -> None:
    from spell_sync.operation_lock import OperationLocked, OperationLockInfo

    wordlist = tmp_path / "project" / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))

    def _locked(*_args, **_kwargs):
        raise OperationLocked(
            OperationLockInfo(1, "2026-01-01", "push", str(wordlist)),
            tmp_path / "project" / ".spell-sync.lock",
        )

    monkeypatch.setattr(
        "spell_sync.project_setup.execute.acquire_operation_lock",
        _locked,
    )
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.FAILED
    assert "lock" in execution.message.lower()


def test_execute_detects_changed_existing_wordlist(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_bytes(b"original\n")
    prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=False))
    wordlist.write_bytes(b"tampered\n")
    execution = execute_project_setup(
        prepared,
        confirmed_setup_id=prepared.setup_id,
    )
    assert execution.outcome is ProjectSetupOutcome.STOPPED_SAFELY
    assert "changed" in execution.message.lower()


def test_controller_execute_setup_updates_wordlist(tmp_path: Path) -> None:
    service = SpellSyncService()
    controller = TuiController(service, CliOptions())
    wordlist = tmp_path / "wordlist.txt"
    controller.set_setup_wordlist(wordlist)
    prepared = controller.prepare_setup_preview()
    execution = controller.execute_setup(prepared)
    assert execution.outcome is ProjectSetupOutcome.COMPLETED
    assert controller.opts.wordlist == str(wordlist)


def test_build_setup_reports_for_all_outcomes() -> None:
    from spell_sync.application.builders import build_setup_operation_report

    prepared = prepare_project_setup(
        SetupDraft(Path("/tmp/x/wordlist.txt"), (), create_wordlist=True)
    )
    for outcome in (
        ProjectSetupOutcome.STOPPED_SAFELY,
        ProjectSetupOutcome.SETUP_INCOMPLETE,
        ProjectSetupOutcome.FAILED,
    ):
        report = build_setup_operation_report(
            ProjectSetupExecution(
                prepared=prepared,
                outcome=outcome,
                message=str(outcome.value),
            )
        )
        assert report.operation == "setup"
