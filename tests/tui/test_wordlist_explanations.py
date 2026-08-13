"""TUI copy for personal word list and custom dictionary scope."""

import unittest

from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from tests.tui.fake_service import fake_service, sample_pull_preview
from tests.tui.test_helpers import wait_for_text


class TestWordlistExplanations(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_explains_custom_dictionaries_and_excludes_built_in(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            content = await wait_for_text(pilot, "#welcome-content", "Welcome")
            text = str(content.render()).lower()
            self.assertIn("personal words", text)
            self.assertIn("built-in", text)
            self.assertIn("never the built-in dictionary that ships", text)

    async def test_wordlist_setup_explains_personal_exceptions(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await pilot.click("#btn-setup")
            content = await wait_for_text(pilot, "#wordlist-content", "What belongs")
            text = str(content.render()).lower()
            self.assertIn("personal", text)
            self.assertIn("built-in", text)

    async def test_storage_strategy_screen_offers_three_approaches(self):
        from spell_sync.tui.screens.setup_welcome_screen import SetupStorageStrategyScreen

        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupStorageStrategyScreen(controller))
            content = await wait_for_text(pilot, "#storage-content", "How will you keep")
            text = str(content.render()).lower()
            self.assertIn("sync", text)
            hint = await wait_for_text(pilot, "#storage-hint", "Simplest")
            self.assertIn("computer", str(hint.render()).lower())
            await pilot.click("#btn-more")
            await wait_for_text(pilot, "#storage-content", "travel")
            await pilot.click("#storage-cloud")
            cloud_hint = await wait_for_text(pilot, "#storage-hint", "Dropbox")
            self.assertIn("icloud", str(cloud_hint.render()).lower())
            await pilot.click("#storage-git")
            git_hint = await wait_for_text(pilot, "#storage-hint", "private Git")
            self.assertIn("private", str(git_hint.render()).lower())
            await pilot.click("#btn-continue")
            self.assertEqual(controller.setup_storage_strategy(), "git_remote")
            await wait_for_text(pilot, "#wordlist-content", "What belongs")

    async def test_targets_screen_scope_notice(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        controller.set_setup_wordlist(controller.setup_wordlist_default())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "wordlist ok"))
            header = await wait_for_text(pilot, "#targets-header", "built-in")
            text = str(header.render()).lower()
            self.assertIn("custom diction", text)
            self.assertIn("not modified", text)

    async def test_pull_preview_mentions_custom_dictionaries(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            content = await wait_for_text(pilot, "#pull-summary", "custom diction")
            text = str(content.render()).lower()
            self.assertIn("application custom diction", text)
            self.assertNotIn("sources used:", text)

    async def test_pull_empty_state_is_clear(self):
        preview = sample_pull_preview(additions=0)
        controller = TuiController(fake_service(pull_preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            content = await wait_for_text(pilot, "#pull-summary", "already")
            text = str(content.render()).lower()
            self.assertIn("no new words to collect", text)
            self.assertIn("custom diction", text)

    async def test_push_preview_includes_filtering_and_redundancy_notices(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            summary = await wait_for_text(pilot, "#preview-content", "Words to add")
            summary_text = str(summary.render()).lower()
            self.assertIn("custom diction", summary_text)
            self.assertIn("most apps", summary_text)
            self.assertIn("filtered subset", summary_text)
            self.assertIn("built-in", summary_text)
            self.assertIn("duplicate custom entries", summary_text)
            self.assertEqual(len(list(app.screen.query("#btn-toggle-details"))), 0)
            self.assertEqual(len(list(app.screen.query("#preview-details"))), 0)

    async def test_narrow_terminal_renders_wordlist_setup(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(72, 28)) as pilot:
            await pilot.click("#btn-setup")
            content = await wait_for_text(pilot, "#wordlist-content", "What belongs")
            self.assertGreater(len(str(content.render())), 40)


if __name__ == "__main__":
    unittest.main()
