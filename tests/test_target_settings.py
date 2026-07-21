"""Target settings load, preview, execute, and safety tests."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from spell_sync.application import SpellSyncService
from spell_sync.application.requests import (
    PrepareTargetSettingsUpdateRequest,
    ProjectRef,
    TargetSettingsRequest,
)
from spell_sync.operation_lock import OperationLocked, OperationLockInfo
from spell_sync.project_setup.discovery import (
    SetupTarget,
    SetupTargetDiscovery,
    discover_setup_targets,
)
from spell_sync.project_setup.draft import ProjectConfigDraft, SafetyConfig
from spell_sync.project_setup.render import render_project_config
from spell_sync.project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsOutcome,
    execute_target_settings_update,
    load_target_settings_snapshot,
    resolve_enabled_targets,
)
from spell_sync.push_journal import file_content_hash
from tests.journal_test_utils import write_test_journal


def _target(
    identifier: str,
    *,
    selectable: bool = True,
    enabled: bool = False,
    status: str = "ok",
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path(f"/tmp/{identifier}.txt"),
        format_name="text",
        detected=True,
        available=True,
        readable=True,
        supported=True,
        enabled_by_default=selectable,
        selectable=selectable,
        word_count=3,
        status=status,
        detail=None,
        enabled=enabled,
    )


def _mock_discovery(enabled: frozenset[str]) -> SetupTargetDiscovery:
    targets = (
        _target("chrome", enabled="chrome" in enabled),
        _target("edge", enabled="edge" in enabled),
        _target("firefox", enabled="firefox" in enabled),
    )
    return SetupTargetDiscovery(
        targets=targets,
        default_enabled=tuple(sorted(enabled)),
    )


@pytest.fixture
def mock_targets():
    def _factory(enabled: frozenset[str]):
        def _discover(*, selected_targets=None, enabled_targets=None):
            return _mock_discovery(enabled_targets or frozenset())

        return patch(
            "spell_sync.project_setup.target_settings.discover_setup_targets",
            side_effect=_discover,
        )

    return _factory


@pytest.fixture
def service() -> SpellSyncService:
    return SpellSyncService(enable_file_logging=False)


def _write_config(
    tmp_path: Path,
    *,
    enabled: tuple[str, ...] = ("chrome",),
) -> tuple[Path, Path]:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    config = tmp_path / "spell-sync.toml"
    names = (
        "editors",
        "chrome",
        "edge",
        "brave",
        "vivaldi",
        "firefox",
        "neovim",
        "jetbrains",
        "hunspell",
        "obsidian",
        "libreoffice",
    )
    lines = [f"{name} = {'true' if name in enabled else 'false'}" for name in names]
    body = (
        "[dictionaries]\n"
        + "\n".join(lines)
        + "\n\n[push]\nstrict = true\n\n[io]\nbackup_keep = 5\n"
    )
    config.write_text(body, encoding="utf-8")
    return wordlist, config


def test_load_target_settings_current_selection(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome", "firefox"))
    with mock_targets(frozenset({"chrome", "firefox"})):
        snapshot = service.load_target_settings(
            TargetSettingsRequest(project=ProjectRef(wordlist=wordlist))
        )
    assert snapshot.enabled_target_ids == frozenset({"chrome", "firefox"})
    assert any(target.identifier == "chrome" and target.enabled for target in snapshot.targets)


def test_prepare_enable_and_disable(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset({"chrome", "edge"}),
            )
        )
    assert prepared.enabled_target_ids == frozenset({"edge"})
    assert prepared.disabled_target_ids == frozenset()
    assert prepared.can_execute is True


def test_prepare_disable_target(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome", "firefox"))
    with mock_targets(frozenset({"chrome", "firefox"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"chrome"})
            )
        )
    assert prepared.disabled_target_ids == frozenset({"firefox"})
    assert prepared.can_execute is True


def test_prepare_unknown_target_id(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset({"chrome", "not-a-target"}),
            )
        )
    assert any("Unknown target identifiers ignored" in warning for warning in prepared.warnings)


def test_prepare_no_changes(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"chrome"})
            )
        )
    assert prepared.can_execute is False
    assert any("No configuration changes" in warning for warning in prepared.warnings)


def test_prepare_zero_targets(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome", "firefox"))
    with mock_targets(frozenset({"chrome", "firefox"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset(),
            ),
        )
    assert prepared.disabled_target_ids == frozenset({"chrome", "firefox"})
    assert prepared.can_execute is True


def test_render_preserves_push_and_io(tmp_path: Path) -> None:
    _write_config(tmp_path, enabled=("chrome",))
    existing = {
        "dictionaries": {"chrome": True},
        "push": {"strict": True, "guard_wordlist_max": 11, "guard_local_min": 22},
        "io": {"backup_keep": 5},
        "neovim": {"mkspell_after_push": True},
    }
    rendered = render_project_config(
        ProjectConfigDraft(1, ("edge",), SafetyConfig(backup_keep=5)),
        existing_config=existing,
    ).decode("utf-8")
    assert "strict = true" in rendered
    assert "guard_wordlist_max = 11" in rendered
    assert "backup_keep = 5" in rendered
    assert "mkspell_after_push = true" in rendered
    assert "edge = true" in rendered
    assert "chrome = false" in rendered


def test_deterministic_rendered_config(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        first = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
        second = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    assert first.rendered_config_bytes == second.rendered_config_bytes
    assert first.update_id == second.update_id


def test_execute_updates_config_only(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, config_path = _write_config(tmp_path, enabled=("chrome",))
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("beta\n", encoding="utf-8")
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.COMPLETED
    text = config_path.read_text(encoding="utf-8")
    assert "edge = true" in text
    assert dictionary.read_text(encoding="utf-8") == "beta\n"
    assert wordlist.read_text(encoding="utf-8") == "alpha\n"


def test_execute_stale_fingerprint(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, config_path = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    execution = service.execute_target_settings_update(
        prepared,
        confirmed_update_id=prepared.update_id,
    )
    assert execution.outcome is TargetSettingsOutcome.STOPPED_SAFELY
    assert "spell-sync.toml changed after the preview was created" in execution.message


def test_execute_wrong_update_id(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    execution = service.execute_target_settings_update(
        prepared,
        confirmed_update_id="wrong-id",
    )
    assert execution.outcome is TargetSettingsOutcome.FAILED


def test_execute_active_operation_lock(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )

    class _Locked:
        def __enter__(self):
            raise OperationLocked(
                OperationLockInfo(pid=999, started="now", command="push", wordlist=str(wordlist)),
                Path("/tmp/lock"),
            )

        def __exit__(self, *args):
            return False

    with patch(
        "spell_sync.project_setup.target_settings.acquire_operation_lock",
        return_value=_Locked(),
    ):
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.FAILED
    assert "project lock" in execution.message


def test_execute_pending_recovery_blocks(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    write_test_journal(wordlist, wordlist_write_started=True)
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    assert prepared.can_execute is False


def test_resolve_enabled_preserves_corrupt_enabled(
    tmp_path: Path,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        discovery = discover_setup_targets(
            selected_targets=("chrome",),
            enabled_targets=frozenset({"chrome"}),
        )
    corrupt = next(target for target in discovery.targets if target.identifier == "chrome")
    corrupt = corrupt.__class__(
        **{
            **corrupt.__dict__,
            "selectable": False,
            "status": "corrupt",
            "enabled": True,
        }
    )
    targets = tuple(
        corrupt if target.identifier == "chrome" else target for target in discovery.targets
    )
    enabled = resolve_enabled_targets(
        targets,
        selected_target_ids=frozenset(),
        previous_target_ids=frozenset({"chrome"}),
    )
    assert enabled == frozenset({"chrome"})


def test_atomic_write_used_for_execute(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, config_path = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
        before = file_content_hash(config_path)
        service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert file_content_hash(config_path) != before


def test_parser_round_trip(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset({"edge", "firefox"}),
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.COMPLETED
    with mock_targets(frozenset({"edge", "firefox"})):
        snapshot = load_target_settings_snapshot(wordlist=wordlist)
    assert snapshot.enabled_target_ids == frozenset({"edge", "firefox"})


def test_load_missing_config(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    snapshot = load_target_settings_snapshot(wordlist=wordlist)
    assert snapshot.load_error == "spell-sync.toml is missing."


def test_load_invalid_config(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (tmp_path / "spell-sync.toml").write_text("[[broken\n", encoding="utf-8")
    snapshot = load_target_settings_snapshot(wordlist=wordlist)
    assert snapshot.load_error is not None


def test_execute_cannot_execute_preview(tmp_path: Path) -> None:
    wordlist, config = _write_config(tmp_path, enabled=("chrome",))
    prepared = PreparedTargetSettingsUpdate(
        update_id="x",
        config_path=config,
        wordlist_path=wordlist,
        selected_target_ids=frozenset({"chrome"}),
        previous_target_ids=frozenset({"chrome"}),
        enabled_target_ids=frozenset(),
        disabled_target_ids=frozenset(),
        rendered_config_bytes=b"",
        config_fingerprint_before=file_content_hash(config),
        warnings=(),
        can_execute=False,
    )
    execution = execute_target_settings_update(prepared, confirmed_update_id="x")
    assert execution.outcome is TargetSettingsOutcome.STOPPED_SAFELY


def test_execute_oserror(tmp_path: Path, service: SpellSyncService, mock_targets) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    with patch(
        "spell_sync.project_setup.target_settings.atomic_write",
        side_effect=OSError("disk full"),
    ):
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.FAILED
    assert "disk full" in execution.message


def test_execute_validation_mismatch(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    with patch(
        "spell_sync.project_setup.target_settings._enabled_from_loaded_config",
        return_value=frozenset({"chrome"}),
    ):
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.FAILED


def test_execute_fingerprint_race_inside_lock(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, config_path = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    original = file_content_hash(config_path)
    calls = {"count": 0}

    def _hash(path: Path) -> str | None:
        calls["count"] += 1
        if calls["count"] <= 1:
            return original
        return "changed"

    with patch(
        "spell_sync.project_setup.target_settings.file_content_hash",
        side_effect=_hash,
    ):
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.STOPPED_SAFELY


def test_safety_from_config_default() -> None:
    from spell_sync.project_setup.target_settings import _safety_from_config

    assert _safety_from_config({}).backup_keep == 3


def test_fingerprint_matches_missing_file() -> None:
    from spell_sync.project_setup.target_settings import _fingerprint_matches

    assert _fingerprint_matches(Path("/tmp/does-not-exist.toml"), None) is True


def test_enabled_from_loaded_config_none() -> None:
    from spell_sync.project_setup.target_settings import _enabled_from_loaded_config

    assert _enabled_from_loaded_config(None) == frozenset()


def test_prepare_missing_config_file(tmp_path: Path, service: SpellSyncService) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    prepared = service.prepare_target_settings_update(
        PrepareTargetSettingsUpdateRequest(
            project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"chrome"})
        )
    )
    assert prepared.can_execute is False
    assert any("missing" in warning.lower() for warning in prepared.warnings)


def test_prepare_invalid_config_blocks(tmp_path: Path, service: SpellSyncService) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (tmp_path / "spell-sync.toml").write_text("[[broken\n", encoding="utf-8")
    prepared = service.prepare_target_settings_update(
        PrepareTargetSettingsUpdateRequest(
            project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"chrome"})
        )
    )
    assert prepared.can_execute is False


def test_execute_invalid_written_config(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
    with patch(
        "spell_sync.project_setup.target_settings.load_config_result",
    ) as load_config:
        from spell_sync.settings import ConfigLoadResult, ConfigStatus

        load_config.return_value = ConfigLoadResult(
            ConfigStatus.SYNTAX_ERROR,
            None,
            (),
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.FAILED


def test_execute_completed_message_enable_and_disable(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    wordlist, _config = _write_config(tmp_path, enabled=("chrome", "firefox"))
    with mock_targets(frozenset({"chrome", "firefox"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
        )
    assert execution.outcome is TargetSettingsOutcome.COMPLETED
    assert "Enabled:" in execution.message
    assert "Disabled:" in execution.message


def test_build_target_settings_reports() -> None:
    from spell_sync.application.builders import build_target_settings_operation_report
    from spell_sync.project_setup.target_settings import (
        PreparedTargetSettingsUpdate,
        TargetSettingsExecution,
        TargetSettingsOutcome,
    )

    prepared = PreparedTargetSettingsUpdate(
        update_id="id-1",
        config_path=Path("/tmp/spell-sync.toml"),
        wordlist_path=Path("/tmp/wordlist.txt"),
        selected_target_ids=frozenset({"edge"}),
        previous_target_ids=frozenset({"chrome", "firefox"}),
        enabled_target_ids=frozenset({"edge"}),
        disabled_target_ids=frozenset({"chrome", "firefox"}),
        rendered_config_bytes=b"",
        config_fingerprint_before="abc",
        warnings=(),
        can_execute=True,
    )
    completed = build_target_settings_operation_report(
        TargetSettingsExecution(prepared, TargetSettingsOutcome.COMPLETED, "done"),
    )
    assert any("Disabled:" in detail for detail in completed.details)
    stopped = build_target_settings_operation_report(
        TargetSettingsExecution(prepared, TargetSettingsOutcome.STOPPED_SAFELY, "stopped"),
    )
    assert stopped.outcome.value == "stopped_safely"
    failed = build_target_settings_operation_report(
        TargetSettingsExecution(prepared, TargetSettingsOutcome.FAILED, "failed"),
    )
    assert failed.outcome.value == "failed"


def test_history_record_for_target_settings() -> None:
    from spell_sync.application.builders import build_target_settings_operation_report
    from spell_sync.diagnostics.history_builder import build_history_record
    from spell_sync.project_setup.target_settings import (
        PreparedTargetSettingsUpdate,
        TargetSettingsExecution,
        TargetSettingsOutcome,
    )

    prepared = PreparedTargetSettingsUpdate(
        update_id="id-1",
        config_path=Path("/tmp/spell-sync.toml"),
        wordlist_path=Path("/tmp/wordlist.txt"),
        selected_target_ids=frozenset({"edge"}),
        previous_target_ids=frozenset({"chrome"}),
        enabled_target_ids=frozenset({"edge"}),
        disabled_target_ids=frozenset({"chrome"}),
        rendered_config_bytes=b"",
        config_fingerprint_before="abc",
        warnings=(),
        can_execute=True,
    )
    execution = TargetSettingsExecution(prepared, TargetSettingsOutcome.COMPLETED, "done")
    report = build_target_settings_operation_report(execution)
    record = build_history_record(report, source=execution)
    assert record.enabled_targets == 1
    stopped = TargetSettingsExecution(prepared, TargetSettingsOutcome.STOPPED_SAFELY, "stopped")
    stopped_report = build_target_settings_operation_report(stopped)
    stopped_record = build_history_record(stopped_report, source=stopped)
    assert stopped_record.outcome == "stopped_safely"


def test_io_int_default_for_invalid_value() -> None:
    from spell_sync.project_setup.render import _io_int, _push_bool, render_project_config

    assert _io_int({"io": {"backup_keep": "bad"}}, "backup_keep", 3) == 3
    assert _push_bool({"push": {"strict": "bad"}}, "strict", True) is True
    rendered = render_project_config(
        ProjectConfigDraft(1, ("chrome",), SafetyConfig()),
        existing_config={
            "push": {"max_removals_without_confirm": 4},
            "io": {"backup_keep": 2},
        },
    ).decode("utf-8")
    assert "max_removals_without_confirm = 4" in rendered


def test_service_target_settings_with_event_sink(
    tmp_path: Path,
    service: SpellSyncService,
    mock_targets,
) -> None:
    from spell_sync.application.events import PresentedEvent

    wordlist, _config = _write_config(tmp_path, enabled=("chrome",))
    events: list[PresentedEvent] = []
    with mock_targets(frozenset({"chrome"})):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist), selected_target_ids=frozenset({"edge"})
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
            event_sink=events.append,
        )
        report = service.build_target_settings_report(execution)
    assert events
    assert report.operation == "targets"


def test_controller_lazy_discovery(tmp_path: Path) -> None:
    from spell_sync.tui.controller import TuiController
    from tests.tui.fake_service import fake_service

    wordlist, _ = _write_config(tmp_path, enabled=("chrome",))
    controller = TuiController(fake_service(), ProjectRef(wordlist=wordlist))
    controller.target_settings_discovery()


def test_unreadable_config_path(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    config = tmp_path / "spell-sync.toml"
    config.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
    config.chmod(0)
    try:
        snapshot = load_target_settings_snapshot(wordlist=wordlist)
    finally:
        config.chmod(stat.S_IWUSR | stat.S_IRUSR)
    assert snapshot.load_error is not None
