#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command integration tests."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from conftest import DEFAULT_OPTS
from service_test_utils import (
    executable_push_preview,
    patch_commands_service,
    patch_recover_service,
    pull_execution,
    pull_preview_executable,
    push_execution,
    recoverable_preview,
    recovery_execution,
    status_snapshot_from_run,
)

import spell_sync.commands as commands
import spell_sync.recover_cmd as recover_mod
from spell_sync.application.reports import RecoveryExecution, RecoveryOutcome, RecoveryStatus
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.log import log as cli_log
from spell_sync.push_journal import RecoverResult
from spell_sync.sync_run import PushResult
from tests.runtime_helpers import make_sync_run, pull_add_from, pull_into_wordlist


class TestCommands(unittest.TestCase):
    def _dictionaries(self, path_a: str, path_b: str):
        return [
            Dictionary("a", path_a, DictionaryFormat.TEXT),
            Dictionary("b", path_b, DictionaryFormat.TEXT),
        ]

    def _write_fixture(self, wordlist, path_a, path_b):
        write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
        write_text_words(path_a, ["alpha"], "utf-8", False, quiet=True)
        write_text_words(
            path_b,
            ["alpha", "beta", "extra"],
            "utf-8",
            False,
            quiet=True,
        )

    def test_cmd_status(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            self._write_fixture(wordlist, path_a, path_b)
            run = make_sync_run(
                wordlist,
                dictionaries=self._dictionaries(path_a, path_b),
            )
            with patch_commands_service(load_status=status_snapshot_from_run(run)):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(commands.cmd_status(DEFAULT_OPTS), 0)
                out = buf.getvalue()
                self.assertIn("a:", out)
                self.assertIn("+1", out)
                self.assertIn("-1", out)
                self.assertNotIn("add (push)", out)

    def test_cmd_status_verbose_shows_words(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            self._write_fixture(wordlist, path_a, path_b)
            run = make_sync_run(
                wordlist,
                dictionaries=self._dictionaries(path_a, path_b),
            )
            snapshot = status_snapshot_from_run(run, include_word_diffs=True)
            with patch_commands_service(load_status=snapshot):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_status(CliOptions(verbose=True))
                    self.assertEqual(code, 0)
                out = buf.getvalue()
                self.assertIn("(verbose)", out)
                self.assertIn("beta", out)
                self.assertIn("extra", out)


class TestWordlistUnreadable(unittest.TestCase):
    def test_pull_aborts_when_wordlist_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = make_sync_run(wordlist, dictionaries=[])
            with patch("spell_sync.push_setup.wordlist_unreadable", return_value=True):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = pull_into_wordlist(run)
                self.assertEqual(result, ExitCode.WORDLIST_UNREADABLE)
                self.assertIn("wordlist unreadable", buf.getvalue())

    def test_cmd_status_returns_wordlist_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            open(wordlist, "w").close()
            run = make_sync_run(wordlist, dictionaries=[])
            with (
                patch("spell_sync.push_setup.wordlist_unreadable", return_value=True),
                patch_commands_service(load_status=status_snapshot_from_run(run)),
            ):
                code = commands.cmd_status(DEFAULT_OPTS)
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))


class TestPartialPushExit(unittest.TestCase):
    def test_run_partial_push_exit_via_command(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            result = PushResult(1, ("a",), ("blocked",))
            preview = executable_push_preview()
            execution = push_execution(result, preview=preview)
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
                patch_commands_service(
                    load_push_preview=preview,
                    execute_push_preview=execution,
                    build_push_report=MagicMock(),
                ),
            ):
                code = commands.cmd_push(DEFAULT_OPTS)
            self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))


class TestPushReviewRemovals(unittest.TestCase):
    def test_push_review_removals_interrupted(self):
        preview = executable_push_preview()
        with (
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "review_removals_for_preview", return_value=None),
            patch_commands_service(load_push_preview=preview),
        ):
            code = commands.cmd_push(CliOptions(review_removals=True))
        self.assertEqual(code, int(ExitCode.SYNC_INTERRUPTED))

    def test_before_push_checks_review_removals_false(self):
        preview = executable_push_preview()
        with patch.object(commands, "review_removals_for_preview", return_value=False):
            result = commands.review_removals_for_preview(preview, interactive=False)
        self.assertFalse(result)

    def test_before_push_checks_running_apps_rejected(self):
        with patch.object(commands, "_running_apps_check_for_push", return_value=False):
            self.assertFalse(commands._running_apps_check_for_push(DEFAULT_OPTS))

    def test_before_push_checks_running_apps_interrupted(self):
        with patch.object(commands, "_running_apps_check_for_push", return_value=None):
            self.assertIsNone(commands._running_apps_check_for_push(DEFAULT_OPTS))


class TestPullAddFrom(unittest.TestCase):
    def test_merges_external_file(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            external = os.path.join(d, "extra.txt")
            Path(external).write_text("beta\ngamma\n", encoding="utf-8")
            run = make_sync_run(wordlist, dictionaries=[])
            result = pull_add_from(run, external)
            self.assertIsInstance(result, tuple)
            before, after = result
            self.assertEqual(before, 1)
            self.assertEqual(after, 3)

    def test_cmd_pull_add_from(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("one\n", encoding="utf-8")
            external = os.path.join(d, "from.txt")
            Path(external).write_text("two\n", encoding="utf-8")
            code = commands.cmd_pull(CliOptions(add_from=external, wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.OK))
            words = read_text_words(wordlist, quiet=True)
            self.assertIn("one", words)
            self.assertIn("two", words)


class TestPushServiceGate(unittest.TestCase):
    def test_cmd_pull_blocked_still_uses_presenter(self) -> None:
        buf = io.StringIO()
        with (
            patch.object(
                commands._SERVICE,
                "mutating_config_exit_code",
                return_value=ExitCode.LINT_FAILED,
            ),
            patch.object(commands._SERVICE, "prepare_pull") as prepare_pull,
            redirect_stdout(buf),
        ):
            code = commands.cmd_pull(CliOptions())
        self.assertEqual(code, int(ExitCode.LINT_FAILED))
        prepare_pull.assert_not_called()
        text = buf.getvalue()
        self.assertIn("=== pull:", text)
        self.assertIn("[ERROR] Collect my words blocked", text)

    def test_cmd_push_returns_blocked_exit_from_service(self) -> None:
        opts = CliOptions(yes=True, json_output=True)
        with patch.object(
            commands._SERVICE, "mutating_config_exit_code", return_value=ExitCode.LINT_FAILED
        ):
            with patch.object(commands._SERVICE, "load_push_preview") as load_preview:
                code = commands._cmd_push_via_service(opts)
        self.assertEqual(code, int(ExitCode.LINT_FAILED))
        load_preview.assert_not_called()

    def test_cmd_push_blocked_human_session_fail(self) -> None:
        preview = executable_push_preview()
        with (
            patch.object(
                commands._SERVICE,
                "mutating_config_exit_code",
                return_value=ExitCode.LINT_FAILED,
            ),
            patch_commands_service(load_push_preview=preview),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(yes=True))
        self.assertEqual(code, int(ExitCode.LINT_FAILED))
        self.assertIn("blocked", buf.getvalue())

    def test_cmd_push_confirm_removals_cancelled_session_abort(self) -> None:
        preview = executable_push_preview()
        with (
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals_for_preview", return_value=None),
            patch_commands_service(load_push_preview=preview),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(yes=True))
        self.assertEqual(code, int(ExitCode.SYNC_INTERRUPTED))
        self.assertIn("cancelled", buf.getvalue().lower())

    def test_cmd_status_quiet_log_no_session_outcome(self) -> None:
        run = make_sync_run("/tmp/w.txt", dictionaries=[])
        with patch_commands_service(load_status=status_snapshot_from_run(run)):
            cli_log.quiet = True
            try:
                code = commands.cmd_status(CliOptions())
            finally:
                cli_log.quiet = False
        self.assertEqual(code, int(ExitCode.OK))

    def test_cmd_pull_quiet_log_done_line(self) -> None:
        preview = pull_preview_executable("/tmp/w.txt", 1, 3)
        execution = pull_execution(1, 3, preview=preview)
        with patch_commands_service(
            prepare_pull=preview,
            execute_pull=execution,
            build_pull_report=MagicMock(),
        ):
            cli_log.quiet = True
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_pull(CliOptions())
            finally:
                cli_log.quiet = False
        self.assertEqual(code, int(ExitCode.OK))

    def test_cmd_init_quiet_log_paths(self) -> None:
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
        from spell_sync.project_setup.prepare import prepare_project_setup

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            draft = SetupDraft(wordlist, (), create_wordlist=True)
            prepared = prepare_project_setup(draft)
            failed = ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.FAILED,
                message="init failed",
            )
            with (
                patch.object(
                    commands.SpellSyncService,
                    "prepare_project_setup",
                    return_value=prepared,
                ),
                patch.object(
                    commands.SpellSyncService, "execute_project_setup", return_value=failed
                ),
                patch.object(
                    commands.SpellSyncService, "build_setup_report", return_value=MagicMock()
                ),
            ):
                cli_log.quiet = True
                try:
                    code = commands.cmd_init(CliOptions(wordlist=str(wordlist)))
                finally:
                    cli_log.quiet = False
            self.assertNotEqual(code, 0)

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            draft = SetupDraft(wordlist, (), create_wordlist=True)
            prepared = prepare_project_setup(draft)
            ok = ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.COMPLETED,
                message="ok",
                created_files=("wordlist.txt",),
            )
            with (
                patch.object(
                    commands.SpellSyncService,
                    "prepare_project_setup",
                    return_value=prepared,
                ),
                patch.object(commands.SpellSyncService, "execute_project_setup", return_value=ok),
                patch.object(
                    commands.SpellSyncService, "build_setup_report", return_value=MagicMock()
                ),
            ):
                cli_log.quiet = True
                try:
                    code = commands.cmd_init(CliOptions(wordlist=str(wordlist)))
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.OK))

    def test_cmd_init_quiet_log_nothing_to_create(self) -> None:
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.prepare import prepare_project_setup

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (Path(d) / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
            draft = SetupDraft(wordlist, (), create_wordlist=False)
            prepared = prepare_project_setup(draft)
            with patch.object(
                commands.SpellSyncService,
                "prepare_project_setup",
                return_value=prepared,
            ):
                cli_log.quiet = True
                try:
                    code = commands.cmd_init(CliOptions(wordlist=str(wordlist)))
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.OK))

    def test_cmd_init_conflict_fails_closed(self) -> None:
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.prepare import prepare_project_setup

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.mkdir()  # conflict: path exists but is not a file
            draft = SetupDraft(wordlist, (), create_wordlist=True)
            prepared = prepare_project_setup(draft)
            self.assertFalse(prepared.can_execute)
            self.assertTrue(prepared.conflicts)
            with patch.object(
                commands.SpellSyncService,
                "prepare_project_setup",
                return_value=prepared,
            ):
                code = commands.cmd_init(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_cmd_lint_failure_emits_unified_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("bad\ndup\nbad\n", encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("spell_sync.commands.run_lint", return_value=ExitCode.LINT_FAILED),
                redirect_stdout(buf),
            ):
                code = commands.cmd_lint(CliOptions(wordlist=str(wordlist), strict=True))
            self.assertEqual(code, int(ExitCode.LINT_FAILED))
            text = buf.getvalue()
            self.assertIn("[ERROR] lint found issues that need attention", text)
            self.assertNotIn("[summary]", text)


class TestRecoverCmdCoverage(unittest.TestCase):
    def test_emit_recover_text_without_session(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = recover_mod._emit_recover_text(
                RecoverResult(("wordlist.txt",), (), ()),
                dry_run=True,
                session=None,
            )
        self.assertEqual(code, int(ExitCode.OK))
        self.assertIn("[done ]", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            recover_mod._emit_recover_text(RecoverResult((), (), ()), dry_run=True, session=None)
        self.assertIn("nothing to restore", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            recover_mod._emit_recover_text(
                RecoverResult(("wordlist.txt",), (), ()),
                dry_run=False,
                session=None,
            )
        self.assertIn("recover restored", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            recover_mod._emit_recover_text(RecoverResult((), (), ()), dry_run=False, session=None)
        self.assertIn("nothing to restore", buf.getvalue())

    def test_recover_cleanup_dry_run_and_failures(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            preview = replace(
                recoverable_preview(str(wordlist)),
                status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
                can_cleanup=True,
            )
            with patch_recover_service(inspect_recovery=preview):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), dry_run=True),
                )
            self.assertEqual(code, int(ExitCode.OK))

            failed = RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="cleanup boom",
            )
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery_cleanup=failed,
                build_recovery_report=MagicMock(),
            ):
                cli_log.quiet = True
                try:
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), yes=True),
                    )
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_discard_and_exit_code_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            corrupt = replace(
                recoverable_preview(str(wordlist)),
                status=RecoveryStatus.CORRUPT_JOURNAL,
                can_recover=False,
                detail="bad header",
            )
            failed_discard = RecoveryExecution(
                preview=corrupt,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="discard failed",
            )
            with patch_recover_service(
                inspect_recovery=corrupt,
                execute_recovery_discard=failed_discard,
                build_recovery_report=MagicMock(),
            ):
                cli_log.quiet = True
                try:
                    code = recover_mod.cmd_recover(
                        CliOptions(
                            wordlist=str(wordlist),
                            discard_corrupt_journal=True,
                        ),
                    )
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

            preview_ok = replace(
                recoverable_preview(str(wordlist)),
                transaction_state="rollback_incomplete",
            )
            execution = RecoveryExecution(
                preview=preview_ok,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="recover aborted.",
            )
            with patch_recover_service(
                inspect_recovery=preview_ok,
                execute_recovery=execution,
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), yes=True, json_output=True),
                    )
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["reason"], "rollback_incomplete")
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_session_abort_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            preview_ok = recoverable_preview(str(wordlist))
            result = RecoverResult((), (), ("wordlist.txt",))
            execution = recovery_execution(result, preview=preview_ok)
            with patch_recover_service(
                inspect_recovery=preview_ok,
                execute_recovery=execution,
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), yes=True),
                    )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertIn("failed", buf.getvalue().lower())

            with (
                patch_recover_service(inspect_recovery=preview_ok),
                patch("sys.stdin.isatty", return_value=False),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertIn("--yes", buf.getvalue())

    def test_recover_quiet_log_abort_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            preview_ok = recoverable_preview(str(wordlist))
            with (
                patch_recover_service(inspect_recovery=preview_ok),
                patch("sys.stdin.isatty", return_value=False),
            ):
                cli_log.quiet = True
                try:
                    code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

            execution = RecoveryExecution(
                preview=preview_ok,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="recover aborted.",
            )
            with patch_recover_service(
                inspect_recovery=preview_ok,
                execute_recovery=execution,
            ):
                cli_log.quiet = True
                try:
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), yes=True),
                    )
                finally:
                    cli_log.quiet = False
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
