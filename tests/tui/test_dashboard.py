"""Dashboard screen headless tests."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from textual.css.query import NoMatches

from spell_sync.application.reports import DashboardIssue, DashboardSeverity
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from spell_sync.tui.screens.logs_screen import LogsScreen
from spell_sync.tui.screens.review_update_screen import ReviewStartScreen
from tests.tui.fake_service import fake_service, sample_dashboard, sample_status
from tests.tui.test_helpers import wait_for_text


class TestDashboardScreen(unittest.IsolatedAsyncioTestCase):
    async def test_ready_state(self):
        controller = TuiController(
            fake_service(
                severity=DashboardSeverity.READY,
                targets_ready=5,
                targets_needs_attention=1,
                targets_disabled=2,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Ready")
            text = str(summary.render())
            self.assertIn("Your personal word list", text)
            self.assertIn("✓ 5 ready", text)
            self.assertIn("! 1 need attention", text)
            self.assertIn("· 2 disabled", text)
            self.assertIn("\n\nApplications\n", text)
            self.assertIn("\n\nStatus\n", text)
            self.assertIn("    ✓ Ready", text)
            self.assertNotIn("✓ 5 ready ·", text)
            self.assertNotIn("Preview", text)

    async def test_warning_state(self):
        issues = (
            DashboardIssue(
                code="empty_wordlist",
                severity=DashboardSeverity.WARNING,
                title="Word list is empty",
                detail="Push will abort.",
            ),
        )
        controller = TuiController(
            fake_service(
                severity=DashboardSeverity.WARNING,
                issues=issues,
                empty_wordlist=True,
                targets_needs_attention=1,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Needs attention")
            self.assertIn("Needs attention", str(summary.render()))
            issues_widget = await wait_for_text(pilot, "#dashboard-issues", "Word list is empty")
            self.assertIn("Word list is empty", str(issues_widget.render()))
            next_step = await wait_for_text(pilot, "#dashboard-next-step", "Add words to my list")
            self.assertIn("empty", str(next_step.render()).lower())
            self.assertEqual(app.screen.query_one("#btn-add-words").variant, "primary")
            self.assertEqual(app.screen.query_one("#btn-review-update").variant, "default")

    async def test_invalid_config_blocked(self):
        issues = (
            DashboardIssue(
                code="invalid_config",
                severity=DashboardSeverity.BLOCKED,
                title="Invalid configuration",
                detail="Missing dictionaries section.",
            ),
        )
        controller = TuiController(
            fake_service(
                config_valid=False,
                severity=DashboardSeverity.BLOCKED,
                issues=issues,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Invalid configuration")
            self.assertIn("Invalid configuration", str(banner.render()))
            self.assertTrue(app.screen.query_one("#btn-pull").disabled)
            self.assertTrue(app.screen.query_one("#btn-extra-words").disabled)
            self.assertTrue(app.screen.query_one("#btn-push").disabled)

    async def test_pending_recovery_with_issue(self):
        issues = (
            DashboardIssue(
                code="pending_recovery",
                severity=DashboardSeverity.BLOCKED,
                title="Pending recovery",
                detail="journal in progress",
            ),
        )
        controller = TuiController(
            fake_service(pending_recovery=True, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            self.assertIn("interrupted update", str(banner.render()).lower())

    async def test_pending_recovery(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            self.assertIn("Pending recovery", str(banner.render()))
            self.assertIn("interrupted update", str(banner.render()))
            recovery_btn = app.screen.query_one("#btn-recovery")
            self.assertTrue(app.screen.query_one("#recovery-menu-item").display)
            self.assertFalse(recovery_btn.disabled)
            self.assertEqual(recovery_btn.variant, "primary")
            self.assertTrue(app.screen.query_one("#btn-pull").disabled)
            self.assertTrue(app.screen.query_one("#btn-extra-words").disabled)
            self.assertTrue(app.screen.query_one("#btn-push").disabled)
            self.assertTrue(app.screen.query_one("#btn-review-update").disabled)

    async def test_cleanup_pending_highlights_recovery_without_blocking(self):
        issues = (
            DashboardIssue(
                code="cleanup_pending",
                severity=DashboardSeverity.WARNING,
                title="Recovery files remain",
                detail="The update finished, but recovery files remain.",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.WARNING, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            issues_widget = await wait_for_text(pilot, "#dashboard-issues", "Recovery files remain")
            self.assertIn("Recovery files remain", str(issues_widget.render()))
            recovery_btn = app.screen.query_one("#btn-recovery")
            self.assertTrue(app.screen.query_one("#recovery-menu-item").display)
            self.assertFalse(recovery_btn.disabled)
            self.assertEqual(recovery_btn.variant, "primary")
            self.assertEqual(str(recovery_btn.label), "Clean up leftover files")
            self.assertFalse(app.screen.query_one("#btn-pull").disabled)
            self.assertFalse(app.screen.query_one("#btn-extra-words").disabled)
            self.assertFalse(app.screen.query_one("#btn-push").disabled)

    async def test_unreadable_wordlist(self):
        issues = (
            DashboardIssue(
                code="unreadable_wordlist",
                severity=DashboardSeverity.BLOCKED,
                title="Word list unreadable",
                detail="Permission denied.",
            ),
        )
        controller = TuiController(
            fake_service(
                wordlist_error=ExitCode.PUSH_ABORT,
                severity=DashboardSeverity.BLOCKED,
                issues=issues,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Word list unreadable")
            self.assertIn("Word list unreadable", str(banner.render()))

    async def test_blocked_issue_list(self):
        issues = (
            DashboardIssue(
                code="operation_lock",
                severity=DashboardSeverity.BLOCKED,
                title="Operation lock active",
                detail="pid 99",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            issues_widget = await wait_for_text(pilot, "#dashboard-issues", "Operation lock")
            self.assertIn("Operation lock active", str(issues_widget.render()))

    async def test_no_duplicate_preview_button(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            with self.assertRaises(NoMatches):
                screen.query_one("#btn-preview")

    async def test_push_opens_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
            await pilot.pause()
            from spell_sync.tui.screens.preview_screen import PreviewScreen

            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_open_review_update_start(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-review-update")
            await pilot.pause()
            self.assertIsInstance(app.screen, ReviewStartScreen)
            body = await wait_for_text(pilot, "#review-body", "Nothing changes until you confirm")
            self.assertIn("Usual path after setup", str(body.render()))
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_open_health(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("h")
            await pilot.pause()
            self.assertIsInstance(app.screen, DoctorScreen)

    async def test_open_history(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-history")))
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_open_targets(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-targets")))
            await pilot.pause()
            from spell_sync.tui.screens.target_settings_screen import TargetSettingsScreen

            self.assertIsInstance(app.screen, TargetSettingsScreen)

    async def test_last_operation_summary(self):
        controller = TuiController(
            fake_service(last_operation_summary="Last: Update my apps — 2 dictionaries updated"),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Last: Update my apps")
            text = str(summary.render())
            self.assertIn("2 dictionaries updated", text)
            self.assertIn("\nStatus\n    ✓ Ready\n    Last: Update my apps", text)

    def test_format_summary_status_outline_unit(self):
        state = sample_dashboard(
            last_operation_summary="Last: Update my apps — 2 dictionaries updated",
            targets_ready=5,
        )
        text = DashboardScreen._format_summary(None, state)  # type: ignore[arg-type]
        self.assertIn("\nApplications\n    ✓ 5 ready\n", text)
        self.assertIn("\nStatus\n    ✓ Ready\n    Last: Update my apps", text)
        # Flush-left overall chip under Applications is the regression class.
        self.assertNotIn("\n✓ Ready\nLast:", text)

    def test_format_summary_unreadable_wordlist_does_not_claim_zero(self):
        from spell_sync.application.product_concepts import WORD_LIST_COUNT_UNREADABLE

        state = sample_dashboard(
            snapshot=sample_status(wordlist_error=ExitCode.PUSH_ABORT),
        )
        text = DashboardScreen._format_summary(None, state)  # type: ignore[arg-type]
        self.assertIn(WORD_LIST_COUNT_UNREADABLE, text)
        self.assertNotIn("0 words", text)
        self.assertNotIn("3 words", text)

    async def test_refresh_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("r")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_keyboard_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("s")
            await pilot.pause()
            from spell_sync.tui.screens.status_screen import StatusScreen

            self.assertIsInstance(app.screen, StatusScreen)

    async def test_status_button_opens_status_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-status")))
            await pilot.pause()
            from spell_sync.tui.screens.status_screen import StatusScreen

            self.assertIsInstance(app.screen, StatusScreen)

    async def test_layout_warning_at_80x24(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            warning = app.screen.query_one("#narrow-warning")
            self.assertEqual(str(warning.render()), "")
            self.assertFalse(warning.display)
            # Empty optional slots must not reserve margin rows above the summary.
            for widget_id in (
                "#narrow-warning",
                "#blocking-banner",
                "#dashboard-next-step",
                "#dashboard-issues",
            ):
                self.assertFalse(app.screen.query_one(widget_id).display)
            summary = app.screen.query_one("#dashboard-summary")
            self.assertNotIn("Spell Sync\n", str(summary.render()))
            self.assertTrue(str(summary.render()).startswith("Your personal word list"))

    async def test_action_hints_align_under_buttons(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            button = app.screen.query_one("#btn-review-update")
            hint = app.screen.query_one("#review-update-hint")
            self.assertTrue(hint.display)
            self.assertEqual(hint.region.x, button.region.x)
            self.assertGreaterEqual(hint.region.width, button.region.width)
            self.assertGreater(hint.region.y, button.region.y)
            self.assertIs(hint.parent, button.parent)

    async def test_extra_words_matches_single_steps_indent(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            add_words = app.screen.query_one("#btn-add-words")
            collect = app.screen.query_one("#btn-pull")
            extra = app.screen.query_one("#btn-extra-words")
            update = app.screen.query_one("#btn-push")
            hint = app.screen.query_one("#extra-words-hint")
            pull_hint = app.screen.query_one("#pull-hint")
            for button in (add_words, collect, extra, update):
                self.assertEqual(button.region.x, collect.region.x)
                self.assertEqual(button.region.width, 36)
            self.assertTrue(hint.display)
            self.assertEqual(hint.region.x, extra.region.x)
            self.assertGreaterEqual(hint.region.width, extra.region.width)
            self.assertGreater(hint.region.y, extra.region.y)
            self.assertIs(hint.parent, extra.parent)
            gap_after_collect = extra.region.y - (pull_hint.region.y + pull_hint.region.height)
            gap_after_extra = update.region.y - (hint.region.y + hint.region.height)
            self.assertEqual(gap_after_collect, gap_after_extra)
            self.assertGreater(gap_after_collect, 0)

    async def test_section_to_first_button_gaps_match(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            labels = list(screen.query(".section-label"))
            first_buttons = [
                screen.query_one("#btn-review-update"),
                screen.query_one("#btn-add-words"),
                screen.query_one("#btn-targets"),
                screen.query_one("#btn-health"),
                screen.query_one("#btn-quit"),
            ]
            self.assertEqual(len(labels), 5)
            self.assertTrue(str(labels[-1].render()).endswith("Exit"))
            gaps = [
                btn.region.y - label.region.y - label.region.height
                for label, btn in zip(labels, first_buttons, strict=True)
            ]
            self.assertTrue(all(gap == gaps[0] for gap in gaps), gaps)
            self.assertGreater(gaps[0], 0)

    async def test_summary_to_usual_path_is_role_break(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            summary = app.screen.query_one("#dashboard-summary")
            usual = next(iter(app.screen.query(".section-label")))
            gap = usual.region.y - summary.region.y - summary.region.height
            # Larger than the uniform label→button gap (role break: facts → actions).
            review = app.screen.query_one("#btn-review-update")
            label_to_button = review.region.y - usual.region.y - usual.region.height
            self.assertGreater(gap, label_to_button)
            # Section chrome is full-intensity text, not a muted caption.
            self.assertNotEqual(
                str(usual.styles.color),
                str(app.screen.query_one("#review-update-hint").styles.color),
            )

    async def test_hidden_recovery_does_not_inflate_section_gap(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            self.assertFalse(screen.query_one("#recovery-menu-item").display)
            labels = list(screen.query(".section-label"))
            # Usual path → Single steps → Manage → Support → Exit
            review_hint = screen.query_one("#review-update-hint")
            gap_to_single = labels[1].region.y - review_hint.region.y - review_hint.region.height
            check_hint = screen.query_one("#status-hint")
            gap_to_manage = labels[2].region.y - check_hint.region.y - check_hint.region.height
            history_hint = screen.query_one("#history-hint")
            gap_to_exit = labels[4].region.y - history_hint.region.y - history_hint.region.height
            self.assertEqual(gap_to_single, gap_to_manage)
            self.assertEqual(gap_to_manage, gap_to_exit)

    async def test_last_menu_item_not_flush_with_footer(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            body = app.screen.query_one("#screen-body")
            body.scroll_end(animate=False)
            await pilot.pause()
            quit_btn = app.screen.query_one("#btn-quit")
            footer = app.screen.query_one("Footer")
            gap = footer.region.y - (quit_btn.region.y + quit_btn.region.height)
            self.assertGreaterEqual(gap, 1)
            css = Path(__file__).resolve().parents[2] / "spell_sync" / "tui" / "app.tcss"
            text = css.read_text(encoding="utf-8")
            self.assertIn("padding: 1 2 1 2;", text)
            self.assertIn("padding: 0 0 1 0;", text)

    async def test_menu_item_focus_within_marks_parent(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            button = app.screen.query_one("#btn-review-update")
            menu = button.parent
            assert menu is not None
            self.assertIn("menu-item", menu.classes)
            button.focus()
            await pilot.pause()
            self.assertTrue(menu.has_focus_within)
            css = Path(__file__).resolve().parents[2] / "spell_sync" / "tui" / "app.tcss"
            self.assertNotIn(".menu-item:focus-within", css.read_text(encoding="utf-8"))

    async def test_layout_warning_below_minimum(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(60, 20)) as pilot:
            warning = await wait_for_text(pilot, "#narrow-warning", "80 by 24")
            self.assertIn("80 by 24", str(warning.render()))
            self.assertTrue(warning.display)

    async def test_recovery_navigation(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            await pilot.click("#btn-recovery")
            await pilot.pause()
            from spell_sync.tui.screens.recovery_screen import RecoveryScreen

            self.assertIsInstance(app.screen, RecoveryScreen)

    async def test_health_and_history_available_during_recovery(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            self.assertFalse(app.screen.query_one("#btn-health").disabled)
            self.assertFalse(app.screen.query_one("#btn-history").disabled)

    async def test_home_wordlist_path_display(self):
        home_wordlist = str(Path.home() / "my-words" / "wordlist.txt")
        service = fake_service()
        service.dashboard_state = sample_dashboard(wordlist_path=home_wordlist)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "~/")
            self.assertIn("~/my-words/wordlist.txt", str(summary.render()))

    async def test_no_targets_configured_message(self):
        controller = TuiController(
            fake_service(
                targets_ready=0,
                targets_needs_attention=0,
                targets_disabled=0,
                targets_unavailable=0,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(
                pilot,
                "#dashboard-summary",
                "No applications configured",
            )
            self.assertIn("No applications configured", str(summary.render()))
            cta = await wait_for_text(pilot, "#dashboard-next-step", "Applications")
            self.assertIn("open Applications", str(cta.render()))
            self.assertEqual(app.screen.query_one("#btn-targets").variant, "primary")
            self.assertEqual(app.screen.query_one("#btn-review-update").variant, "default")

    async def test_unavailable_targets_display(self):
        controller = TuiController(
            fake_service(targets_unavailable=2),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "2 unavailable")
            self.assertIn("2 unavailable", str(summary.render()))

    async def test_blocked_write_actions_notify(self):
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, pending_recovery=True),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.action_open_review_update()
            screen.action_open_preview()
            await pilot.pause()

    async def test_corrupt_journal_banner(self):
        issues = (
            DashboardIssue(
                code="corrupt_journal",
                severity=DashboardSeverity.BLOCKED,
                title="Corrupt journal",
                detail="bad",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            banner = await wait_for_text(
                pilot, "#blocking-banner", "Damaged interrupted-update record"
            )
            self.assertIn("Damaged interrupted-update record", str(banner.render()))


if __name__ == "__main__":
    unittest.main()
