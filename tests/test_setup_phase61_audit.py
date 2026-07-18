"""Pre-audit checks for Phase 6.1 setup target selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.discovery import (
    SetupTarget,
    SetupTargetDiscovery,
    config_draft_from_targets,
)
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.project_setup.render import render_project_config
from spell_sync.project_setup.selection import SetupSelection, toggle_target
from spell_sync.tui.controller import TuiController
from tests.tui.fake_service import fake_service


def _target(identifier: str, *, selectable: bool = True) -> SetupTarget:
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
        word_count=1,
        status="ok",
        detail=None,
    )


def test_setup_id_includes_selection_paths_and_bytes(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    first = prepare_project_setup(SetupDraft(wordlist, ("chrome",), create_wordlist=True))
    second = prepare_project_setup(SetupDraft(wordlist, ("firefox",), create_wordlist=True))
    assert first.setup_id != second.setup_id
    kept = prepare_project_setup(
        SetupDraft(
            wordlist,
            ("chrome",),
            create_wordlist=True,
        )
    )
    wordlist.write_text("alpha\n", encoding="utf-8")
    with_fingerprint = prepare_project_setup(
        SetupDraft(wordlist, ("chrome",), create_wordlist=False)
    )
    assert kept.setup_id != with_fingerprint.setup_id


def test_stale_prepared_setup_rejected(tmp_path: Path) -> None:
    from spell_sync.project_setup.execute import execute_project_setup

    wordlist = tmp_path / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, ("chrome",), create_wordlist=True))
    execution = execute_project_setup(prepared, confirmed_setup_id="wrong")
    assert execution.outcome.value == "failed"


def test_disabled_target_cannot_toggle_in_core() -> None:
    discovery = SetupTargetDiscovery(
        targets=(_target("chrome"), _target("cursor", selectable=False)),
        default_enabled=("chrome",),
    )
    selection = SetupSelection(frozenset({"chrome"}))
    updated = toggle_target(selection, discovery, "cursor")
    assert updated == selection


def test_render_project_config_is_deterministic() -> None:
    from spell_sync.project_setup.draft import ProjectConfigDraft, SafetyConfig

    draft = ProjectConfigDraft(1, ("firefox", "chrome"), SafetyConfig())
    first = render_project_config(draft)
    second = render_project_config(draft)
    assert first == second
    assert first.index(b"chrome = true") < first.index(b"firefox = true")


def test_unknown_target_id_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown setup target"):
        config_draft_from_targets(("not-a-real-target",))


def test_zero_selected_targets_supported(tmp_path: Path) -> None:
    prepared = prepare_project_setup(
        SetupDraft(tmp_path / "wordlist.txt", (), create_wordlist=True)
    )
    assert prepared.can_execute
    assert prepared.enabled_targets == ()


def test_setup_session_cleared_after_success() -> None:
    service = fake_service()
    controller = TuiController(service, CliOptions())
    controller.set_setup_wordlist(Path("/tmp/wl.txt"))
    controller.clear_setup_session()
    assert controller.setup_selected_targets == ()
    assert controller.setup_selection().selected_target_ids == frozenset()


async def _disabled_row_toggle_blocked() -> None:
    from spell_sync.tui.app import SpellSyncApp
    from spell_sync.tui.screens.setup_targets_screen import SetupTargetRowWidget, SetupTargetsScreen

    discovery = SetupTargetDiscovery(
        targets=(_target("chrome"), _target("cursor", selectable=False)),
        default_enabled=("chrome",),
    )
    service = fake_service()
    service.discover_setup_targets = MagicMock(return_value=discovery)
    controller = TuiController(service, CliOptions())
    controller.set_setup_wordlist(Path("/tmp/setup/wordlist.txt"))
    controller._setup_discovery = discovery
    app = SpellSyncApp(controller)
    async with app.run_test(size=(100, 32)) as pilot:
        app.push_screen(SetupTargetsScreen(controller, "detail"))
        await pilot.pause()
        row = app.screen.query_one("#target-row-cursor", SetupTargetRowWidget)
        row.post_message(SetupTargetRowWidget.Toggled("cursor"))
        row.key_space()
        await pilot.pause()
        assert "cursor" not in controller.setup_selected_targets


def test_disabled_target_blocked_via_tui() -> None:
    import asyncio

    asyncio.run(_disabled_row_toggle_blocked())
