"""Target Details screen tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from spell_sync.application.requests import ProjectRef
from spell_sync.application.target_details import build_target_details, format_target_details_text
from spell_sync.project_setup.discovery import SetupTarget
from spell_sync.project_setup.target_settings import TargetSettingsSnapshot
from spell_sync.target_capabilities import TargetFilterKind, capability_by_id
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.setup_targets_screen import SetupTargetRowWidget
from spell_sync.tui.screens.target_details_screen import TargetDetailsScreen
from spell_sync.tui.screens.target_settings_screen import TargetSettingsScreen
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


def _target(
    identifier: str,
    *,
    status: str = "ok",
    supported: bool = True,
    path: Path | None = None,
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=path or Path("/Users/private-name/Library/Chrome/dict.txt"),
        format_name="chrome",
        detected=True,
        available=status == "ok",
        readable=status in {"ok", "empty"},
        supported=supported,
        enabled_by_default=True,
        selectable=True,
        word_count=3,
        status=status,
        detail=None,
        enabled=True,
    )


class TestTargetDetails(unittest.IsolatedAsyncioTestCase):
    def test_stable_capability_values(self) -> None:
        target = _target("chrome")
        details = build_target_details(target)
        capability = capability_by_id("chrome")
        assert capability is not None
        self.assertEqual(details.pull_supported, capability.pull_supported)
        self.assertEqual(details.push_supported, capability.push_supported)
        self.assertIn("Chrome", format_target_details_text(details))

    def test_latin_filtering_label(self) -> None:
        capability = capability_by_id("win_spelling")
        assert capability is not None
        self.assertEqual(capability.filter_kind, TargetFilterKind.LOCALE_SPECIFIC)

    def test_redacted_home_path(self) -> None:
        target = _target("chrome")
        details = build_target_details(target)
        text = format_target_details_text(details)
        self.assertNotIn("/Users/private-name", text)
        if details.custom_dictionary_path:
            self.assertTrue(
                details.custom_dictionary_path.startswith("~/")
                or details.custom_dictionary_path.startswith("<external>/")
            )

    def test_automated_validation_from_packaged_data(self) -> None:
        target = _target("chrome")
        details = build_target_details(target)
        text = format_target_details_text(details)
        self.assertEqual(details.automated_validation, "pass")
        self.assertEqual(details.manual_validation, "not-run")
        self.assertIn("pass", text.lower())

    def test_corrupt_target_suggested_action(self) -> None:
        target = _target("chrome", status="corrupt")
        details = build_target_details(target, suggested_action="Repair dictionary file.")
        text = format_target_details_text(details)
        self.assertIn("Corrupt", details.runtime_state)
        self.assertIn("Repair dictionary file.", text)

    async def test_open_details_by_keyboard(self) -> None:
        snapshot = TargetSettingsSnapshot(
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            targets=(_target("chrome"),),
            enabled_target_ids=frozenset({"chrome"}),
        )
        service = fake_service()
        service.load_target_settings = MagicMock(return_value=snapshot)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await wait_for_text(pilot, "#target-row-chrome", "Chrome")
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            row = screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            row.focus()
            await pilot.press("enter")
            await wait_for_text(pilot, "#target-details-content", "Capabilities")
            content = str(app.screen.query_one("#target-details-content").render())
            self.assertNotIn("secret-token-like-value", content)
            self.assertNotIn("/Users/private-name", content)

    async def test_open_details_screen_directly(self) -> None:
        snapshot = TargetSettingsSnapshot(
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            targets=(_target("firefox", status="unreadable"),),
            enabled_target_ids=frozenset({"firefox"}),
        )
        service = fake_service()
        service.load_target_settings = MagicMock(return_value=snapshot)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await app.push_screen(TargetDetailsScreen(controller, "firefox"))
            content = await wait_for_text(pilot, "#target-details-content", "Unreadable")
            self.assertIn("Unreadable", str(content.render()))
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, TargetSettingsScreen)


if __name__ == "__main__":
    unittest.main()
