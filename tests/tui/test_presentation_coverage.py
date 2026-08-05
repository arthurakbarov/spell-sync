"""Targeted coverage for presentation modules that gate full CI at ≥98% lines."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Button

from spell_sync.cli_options import CliOptions
from spell_sync.diagnostics.history_record import OperationHistoryRecord
from spell_sync.diagnostics.technical_event_log import ParsedTechnicalLogEvent
from spell_sync.diagnostics.technical_event_model import (
    EventCategory,
    EventId,
    EventPhase,
    EventReason,
    EventSeverity,
    OperationKind,
)
from spell_sync.tui import layout
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.path_picker import WordlistPathPicker
from spell_sync.tui.path_suggester import _listing_context, complete_path, list_path_completions
from spell_sync.tui.screens import logs_screen
from spell_sync.tui.screens.pull_confirm_screen import PullConfirmScreen
from spell_sync.tui.screens.removals_screen import RemovalsScreen
from spell_sync.tui.screens.setup_welcome_screen import SetupOpenProjectScreen
from tests.tui.fake_service import fake_service, sample_pull_preview


class TestLayoutHints(unittest.TestCase):
    def test_expected_duration_hint_minutes(self) -> None:
        layout.EXPECTED_DURATION_SECONDS["slow-op"] = 90
        try:
            hint = layout.expected_duration_hint("slow-op")
            assert hint is not None
            self.assertIn("minute", hint)
            layout.EXPECTED_DURATION_SECONDS["one-min"] = 60
            self.assertIn("1 minute", layout.expected_duration_hint("one-min") or "")
        finally:
            layout.EXPECTED_DURATION_SECONDS.pop("slow-op", None)
            layout.EXPECTED_DURATION_SECONDS.pop("one-min", None)

    def test_primary_back_actions_orders_buttons(self) -> None:
        bar = layout.primary_back_actions(
            primary_label="Go",
            primary_id="btn-go",
            extra=(Button("Extra", id="btn-extra"),),
        )
        pending = list(bar._pending_children)
        ids = [child.id for child in pending if isinstance(child, Button)]
        self.assertEqual(ids, ["btn-go", "btn-extra", "btn-back"])

    def test_primary_back_actions_without_back(self) -> None:
        bar = layout.primary_back_actions(
            primary_label="Go",
            primary_id="btn-go",
            back=False,
        )
        pending = list(bar._pending_children)
        ids = [child.id for child in pending if isinstance(child, Button)]
        self.assertEqual(ids, ["btn-go"])


class TestPathSuggesterEdges(unittest.TestCase):
    def test_listdir_oserror_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def boom(_path: str) -> list[str]:
                raise OSError("denied")

            original = os.listdir
            os.listdir = boom  # type: ignore[assignment]
            try:
                self.assertEqual(list_path_completions(str(root) + "/"), [])
            finally:
                os.listdir = original

    def test_hides_dotfiles_without_dot_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".secret").mkdir()
            (root / "public").mkdir()
            hits = list_path_completions(str(root) + "/")
            prompts = [hit.prompt for hit in hits]
            self.assertIn("public/", prompts)
            self.assertNotIn(".secret/", prompts)

    def test_raw_tilde_slash_home_style(self) -> None:
        # Exercise _format_value home branch for empty/"~/" typed values.
        home = Path.home()
        (home / "Documents").mkdir(exist_ok=True)
        hits = list_path_completions("~/")
        self.assertTrue(any(hit.value.startswith("~/") for hit in hits))

    def test_listing_context_tilde_only(self) -> None:
        directory, prefix, formatted = _listing_context("~")
        self.assertEqual(directory, Path.home())
        self.assertEqual(prefix, "")
        self.assertEqual(formatted, "~/")

    def test_listing_context_backslash_trailing(self) -> None:
        _directory, prefix, formatted = _listing_context("somewhere\\")
        self.assertEqual(prefix, "")
        self.assertTrue(formatted.endswith("/"))

    def test_complete_path_empty(self) -> None:
        self.assertIsNone(complete_path("/no/such/prefix-zzz"))

    def test_is_dir_oserror_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spooky = root / "spooky"
            spooky.mkdir()
            original = Path.is_dir

            def flaky(self: Path) -> bool:
                if self.name == "spooky":
                    raise OSError("stat failed")
                return original(self)

            Path.is_dir = flaky  # type: ignore[method-assign]
            try:
                hits = list_path_completions(str(root) + "/")
            finally:
                Path.is_dir = original  # type: ignore[method-assign]
            self.assertEqual(hits, [])


class _PickerApp(App[None]):
    def compose(self) -> ComposeResult:
        yield WordlistPathPicker(value="")


class TestPathPickerWidget(unittest.IsolatedAsyncioTestCase):
    async def test_apply_highlighted_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha").mkdir()
            (root / "beta").mkdir()
            app = _PickerApp()
            async with app.run_test(size=(100, 40)) as pilot:
                picker = app.screen.query_one(WordlistPathPicker)
                picker.path_value = str(root) + "/"
                await pilot.pause()
                self.assertGreaterEqual(len(picker._completions), 2)
                self.assertTrue(picker.apply_highlighted())
                self.assertTrue(picker.path_value.endswith("/"))
                picker.path_value = str(root / "nope")
                await pilot.pause()
                self.assertFalse(picker.apply_highlighted())

    async def test_single_completion_option_select_and_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "onlydir").mkdir()
            app = _PickerApp()
            async with app.run_test(size=(100, 40)) as pilot:
                picker = app.screen.query_one(WordlistPathPicker)
                # Not yet mounted path is covered before compose finishes? refresh when empty.
                unmounted = WordlistPathPicker()
                unmounted.refresh_completions()
                picker.path_value = str(root / "only")
                await pilot.pause()
                self.assertEqual(len(picker._completions), 1)
                option_list = picker.query_one("#path-complete-list")
                option_list.highlighted = None
                self.assertTrue(picker.apply_highlighted())

                class _Evt:
                    def __init__(self, input_id: str) -> None:
                        self.input = type("I", (), {"id": input_id})()

                picker.on_input_changed(_Evt("other"))  # type: ignore[arg-type]
                picker.on_input_changed(_Evt("wordlist-input"))  # type: ignore[arg-type]
                await pilot.pause()
                picker.path_value = str(root) + "/"
                await pilot.pause()
                picker.on_option_list_option_selected(type("E", (), {"option_index": 0})())  # type: ignore[arg-type]
                await pilot.pause()
                picker.on_option_list_option_selected(type("E", (), {"option_index": 99})())  # type: ignore[arg-type]


class TestLogsHelpers(unittest.TestCase):
    def _record(self, **kwargs: object) -> OperationHistoryRecord:
        base: dict[str, object] = {
            "schema_version": 1,
            "record_id": "rec-1",
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "operation": "push",
            "outcome": "success",
            "duration_ms": 10,
            "warnings": 0,
            "added_words": 0,
            "updated_targets": 0,
            "created_files": 0,
            "restored_files": 0,
        }
        base.update(kwargs)
        return OperationHistoryRecord(**base)  # type: ignore[arg-type]

    def test_summary_and_detail_branches(self) -> None:
        self.assertIn(
            "added",
            logs_screen._summary_line(self._record(operation="pull", added_words=3)),
        )
        self.assertIn("updated", logs_screen._summary_line(self._record(updated_targets=2)))
        self.assertIn(
            "files",
            logs_screen._summary_line(self._record(operation="setup", created_files=1)),
        )
        self.assertIn(
            "restored",
            logs_screen._summary_line(self._record(operation="recover", restored_files=4)),
        )
        self.assertIn("Success", logs_screen._summary_line(self._record(operation="push")))
        self.assertEqual(
            logs_screen._history_detail(self._record(operation="pull", added_words=1)),
            "1 added",
        )
        self.assertEqual(
            logs_screen._history_detail(self._record(updated_targets=2)),
            "2 updated",
        )
        self.assertEqual(
            logs_screen._history_detail(self._record(operation="setup", created_files=3)),
            "3 files",
        )
        self.assertEqual(
            logs_screen._history_detail(self._record(operation="recover", restored_files=5)),
            "5 restored",
        )
        self.assertEqual(logs_screen._history_detail(self._record()), "Success")

    def test_technical_event_message_parts(self) -> None:
        event = ParsedTechnicalLogEvent(
            event_id=EventId.PUSH_COMPLETED,
            operation=OperationKind.PUSH,
            category=EventCategory.LIFECYCLE,
            severity=EventSeverity.INFO,
            timestamp="2026-01-01T00:00:00Z",
            phase=EventPhase.EXECUTING,
            reason=EventReason.CONFLICT_DETECTED,
        )
        text = logs_screen._technical_event_message(event)
        self.assertIn("push", text.lower())
        self.assertIn("conflict", text.lower())


class TestConfirmAndRemovals(unittest.IsolatedAsyncioTestCase):
    async def test_pull_confirm_cancel_action(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = PullConfirmScreen(controller, sample_pull_preview())
            app.push_screen(screen)
            await pilot.pause()
            screen.action_cancel()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, PullConfirmScreen)

    async def test_pull_confirm_buttons_via_handler(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        preview = sample_pull_preview()
        controller.active_pull_preview = lambda: preview  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = PullConfirmScreen(controller, preview)
            app.push_screen(screen)
            await pilot.pause()

            class _Btn:
                def __init__(self, button_id: str) -> None:
                    self.id = button_id

            class _Evt:
                def __init__(self, button_id: str) -> None:
                    self.button = _Btn(button_id)

            screen.on_button_pressed(_Evt("btn-cancel"))  # type: ignore[arg-type]
            await pilot.pause()
            app.push_screen(PullConfirmScreen(controller, preview))
            await pilot.pause()
            screen2 = app.screen
            assert isinstance(screen2, PullConfirmScreen)
            screen2.on_button_pressed(_Evt("btn-run"))  # type: ignore[arg-type]
            await pilot.pause()

    async def test_clear_history_cancel_action(self) -> None:
        from spell_sync.tui.screens.logs_screen import ClearHistoryConfirmScreen, LogsScreen

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            logs = LogsScreen(controller)
            app.push_screen(logs)
            await pilot.pause()
            confirm = ClearHistoryConfirmScreen(controller, logs)
            app.push_screen(confirm)
            await pilot.pause()
            confirm.action_cancel()
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_removals_back_button(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RemovalsScreen("chrome", frozenset({"alpha"})))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, RemovalsScreen)

    async def test_removals_empty_list(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RemovalsScreen("chrome", frozenset()))
            await pilot.pause()
            body = str(app.screen.query_one("#removals-content").render())
            self.assertIn("no words", body.lower())


class TestSetupPathComplete(unittest.IsolatedAsyncioTestCase):
    async def test_tab_applies_highlighted_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
            controller = TuiController(fake_service(), CliOptions())
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                screen = SetupOpenProjectScreen(controller)
                app.push_screen(screen)
                await pilot.pause()
                picker = screen.query_one(WordlistPathPicker)
                picker.path_value = str(root) + "/"
                await pilot.pause()
                screen.action_complete_path()
                await pilot.pause()
                self.assertTrue(picker.path_value)

    async def test_setup_action_backs(self) -> None:
        from spell_sync.tui.screens.setup_welcome_screen import (
            ChangeWordlistScreen,
            SetupStorageStrategyScreen,
            SetupWordlistScreen,
        )

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            for screen_cls in (
                SetupStorageStrategyScreen,
                SetupWordlistScreen,
                SetupOpenProjectScreen,
                ChangeWordlistScreen,
            ):
                app.push_screen(screen_cls(controller))
                await pilot.pause()
                app.screen.action_back()
                await pilot.pause()

    async def test_complete_path_swallows_query_errors(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        screen = SetupOpenProjectScreen(controller)
        # Not mounted: query_one raises and must be swallowed.
        screen.action_complete_path()


if __name__ == "__main__":
    unittest.main()
