#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for command_helpers, paths resolution, and commands coverage."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from conftest import DEFAULT_OPTS
from service_test_utils import (
    executable_push_preview,
    patch_commands_service,
    pull_execution,
    pull_preview_executable,
    push_execution,
    status_snapshot_from_run,
)

import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
from spell_sync.application.reports import PullPreview
from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import finish_push, wordlist_file_for
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.paths import resolve_wordlist_path
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus, PushJournal
from spell_sync.settings import ConfigDiagnostic, ConfigLoadResult, ConfigStatus
from spell_sync.sync_run import PushResult
from tests.runtime_helpers import make_sync_run


class TestResolveWordlistPath(unittest.TestCase):
    def test_explicit_path(self):
        self.assertEqual(
            resolve_wordlist_path("/tmp/custom.txt"),
            Path("/tmp/custom.txt"),
        )

    def test_default_uses_project_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            (root / "spell_sync").mkdir()
            sub = root / "nested"
            sub.mkdir()
            with patch("spell_sync.paths.Path.cwd", return_value=sub):
                self.assertEqual(resolve_wordlist_path(), root / "wordlist.txt")

    def test_cli_options_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            custom = os.path.join(d, "words.txt")
            Path(custom).write_text("a\n", encoding="utf-8")
            opts = CliOptions(wordlist=custom)
            self.assertEqual(wordlist_file_for(opts), Path(custom))

    def test_sync_run_for_uses_resolved_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            custom = os.path.join(d, "words.txt")
            Path(custom).write_text("a\n", encoding="utf-8")
            from spell_sync.application.requests import ProjectRef
            from spell_sync.application.runtime_resolver import RuntimeResolver
            from spell_sync.sync_run import sync_run_for

            resolved = RuntimeResolver().resolve_read(ProjectRef(wordlist=Path(custom)))
            run = sync_run_for(resolved)
            self.assertEqual(str(run.wordlist_file), custom)

    def test_finish_push_json_partial(self):
        result = PushResult(2, ("a",), ("skip",))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = finish_push(result, CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["exit"], int(ExitCode.PARTIAL_PUSH))
        self.assertIn("skipped_reasons", payload)
        self.assertIn("skipped_details", payload)


class TestCommandHelpers(unittest.TestCase):
    def test_dictionaries_label_plurals(self):
        cases = {
            0: "0 dictionaries",
            1: "1 dictionary",
            2: "2 dictionaries",
            5: "5 dictionaries",
            11: "11 dictionaries",
            21: "21 dictionaries",
            22: "22 dictionaries",
        }
        for count, expected in cases.items():
            with self.subTest(count=count):
                self.assertEqual(command_helpers.dictionaries_label(count), expected)

    def test_guard_exit_code(self):
        self.assertIsNone(command_helpers.guard_exit_code(True, cancelled=ExitCode.CANCELLED))
        self.assertEqual(
            command_helpers.guard_exit_code(None, cancelled=ExitCode.CANCELLED),
            int(ExitCode.SYNC_INTERRUPTED),
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.guard_exit_code(False, cancelled=ExitCode.CANCELLED)
        self.assertEqual(code, int(ExitCode.CANCELLED))
        self.assertIn("Cancelled", buf.getvalue())

    def test_confirm_push_removals_non_interactive_aborts(self):
        from unittest.mock import MagicMock

        from spell_sync.runtime_settings import RuntimeSettings
        from tests.tui.fake_service import sample_preview

        prepared = MagicMock()
        prepared.max_removals.return_value = 100
        prepared.ctx.settings = RuntimeSettings.defaults()
        preview = sample_preview(prepared=prepared, removals=100)
        with (
            patch.object(command_helpers, "push_max_removals_without_confirm", return_value=5),
            patch.object(command_helpers.sys, "stdin") as stdin,
        ):
            stdin.isatty.return_value = False
            self.assertFalse(
                command_helpers.confirm_push_removals_for_preview(
                    preview, CliOptions(json_output=False)
                )
            )

    def test_invalid_config_exit_from_result_allows_valid_config(self):
        valid = ConfigLoadResult(ConfigStatus.VALID, {}, ())
        self.assertIsNone(
            command_helpers.invalid_config_exit_from_result(CliOptions(), "push", valid)
        )

    def test_invalid_config_exit_from_result_json(self):
        invalid = ConfigLoadResult(
            ConfigStatus.SYNTAX_ERROR,
            None,
            (ConfigDiagnostic("spell-sync.toml", "bad", ConfigStatus.SYNTAX_ERROR),),
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.invalid_config_exit_from_result(
                CliOptions(json_output=True),
                "push",
                invalid,
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "invalid_config")

    def test_invalid_config_exit_from_result_text(self):
        invalid = ConfigLoadResult(
            ConfigStatus.SYNTAX_ERROR,
            None,
            (ConfigDiagnostic("spell-sync.toml", "bad", ConfigStatus.SYNTAX_ERROR),),
        )
        code = command_helpers.invalid_config_exit_from_result(
            CliOptions(json_output=False),
            "push",
            invalid,
        )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_unfinished_journal_exit_from_result_cli_paths(self):
        opts_json = CliOptions(json_output=True)
        opts_text = CliOptions(json_output=False)
        absent = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        completed = JournalLoadResult(JournalLoadStatus.VALID_COMPLETED, None)
        self.assertIsNone(
            command_helpers.unfinished_journal_exit_from_result(opts_json, "recover", absent)
        )
        self.assertIsNone(
            command_helpers.unfinished_journal_exit_from_result(opts_json, "push", absent)
        )
        self.assertIsNone(
            command_helpers.unfinished_journal_exit_from_result(opts_json, "push", completed)
        )

        corrupt = JournalLoadResult(JournalLoadStatus.CORRUPT, None, detail="bad json")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.unfinished_journal_exit_from_result(
                opts_json,
                "push",
                corrupt,
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "corrupt_journal")

        with patch.object(command_helpers.log, "abort") as abort:
            code = command_helpers.unfinished_journal_exit_from_result(
                opts_text,
                "push",
                corrupt,
                wordlist=Path("/tmp/w.txt"),
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        abort.assert_called_once()

        journal = PushJournal(
            schema_version=1,
            transaction_id="tx",
            command="push",
            pid=99,
            started="2026-01-01T00:00:00+00:00",
            state="writing",
            wordlist="/tmp/w.txt",
            wordlist_hash_before=None,
            wordlist_hash_after=None,
            wordlist_backup_path=None,
        )
        in_progress = JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.unfinished_journal_exit_from_result(
                opts_json,
                "push",
                in_progress,
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "unfinished_transaction")

        with patch.object(command_helpers.log, "abort") as abort:
            code = command_helpers.unfinished_journal_exit_from_result(
                opts_text,
                "push",
                in_progress,
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        abort.assert_called_once()

    def test_unfinished_journal_exit_from_result_for_recovers(self):
        journal = PushJournal(
            schema_version=1,
            transaction_id="tx",
            command="push",
            pid=99,
            started="2026-01-01T00:00:00+00:00",
            state="writing",
            wordlist="/tmp/w.txt",
            wordlist_hash_before=None,
            wordlist_hash_after=None,
            wordlist_backup_path=None,
        )
        in_progress = JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal)
        from spell_sync import mutation_guards as mutation_guards_mod

        self.assertIsNone(
            mutation_guards_mod.unfinished_journal_exit_from_result_for(
                "recover",
                in_progress,
            )
        )


class TestCommandsJson(unittest.TestCase):
    def test_cmd_pull_json(self):
        preview = pull_preview_executable("/tmp/x", 1, 3)
        execution = pull_execution(1, 3, preview=preview)
        with patch_commands_service(
            prepare_pull=preview,
            execute_pull=execution,
            build_pull_report=MagicMock(),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(CliOptions(json_output=True))
            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["added"], 2)

    def test_cmd_pull_abort_json(self):
        preview = pull_preview_executable("/tmp/x", 0, 0)
        preview = PullPreview(
            wordlist_path="/tmp/x",
            additions=0,
            before_count=0,
            after_count=0,
            sources_used=(),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="2026-01-01T00:00:00+00:00",
            plan_identifier="blocked",
            merged_words=(),
            wordlist_error=ExitCode.WORDLIST_UNREADABLE,
        )
        with patch_commands_service(prepare_pull=preview):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))
            self.assertEqual(json.loads(buf.getvalue())["exit"], int(ExitCode.WORDLIST_UNREADABLE))

    def test_cmd_push_json_success(self):
        result = PushResult(2, ("a", "b"), ())
        preview = executable_push_preview()
        execution = push_execution(result, preview=preview)
        with (
            patch.object(commands, "warn_missing_optional_apps"),
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
            patch_commands_service(
                load_push_preview=preview,
                execute_push_preview=execution,
                build_push_report=MagicMock(),
            ),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(json_output=True))
            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["written"], ["a", "b"])
            self.assertEqual(data["exit"], 0)

    def test_cmd_push_json_abort(self):
        preview = executable_push_preview()
        execution = push_execution(ExitCode.PUSH_ABORT, preview=preview)
        with (
            patch.object(commands, "warn_missing_optional_apps"),
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
            patch_commands_service(
                load_push_preview=preview,
                execute_push_preview=execution,
                build_push_report=MagicMock(),
            ),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_cmd_push_dry_run_json_skips_diff_print(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            result = PushResult(1, ("a",), ())
            preview = executable_push_preview()
            execution = push_execution(result, preview=preview)
            with (
                patch_commands_service(
                    load_push_preview=preview,
                    execute_push_dry_run=execution,
                    load_status=status_snapshot_from_run(run),
                ),
                patch.object(commands, "warn_missing_optional_apps"),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(
                        CliOptions(dry_run=True, json_output=True),
                    )
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(data["dry_run"])
            self.assertNotIn("stale", buf.getvalue())

    def test_cmd_lint_json(self):
        with patch.object(commands, "run_lint", return_value=ExitCode.LINT_FAILED):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_lint(CliOptions(json_output=True, strict=True))
            self.assertEqual(code, int(ExitCode.LINT_FAILED))
            self.assertEqual(json.loads(buf.getvalue())["exit"], int(ExitCode.LINT_FAILED))


class TestCommandsSyncFlow(unittest.TestCase):
    def test_cmd_pull_text_success(self):
        preview = pull_preview_executable("/tmp/x", 2, 5)
        execution = pull_execution(2, 5, preview=preview)
        with patch_commands_service(
            prepare_pull=preview,
            execute_pull=execution,
            build_pull_report=MagicMock(),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(DEFAULT_OPTS)
            self.assertEqual(code, 0)
            self.assertIn("wordlist:", buf.getvalue())

    def test_running_apps_check_for_push_delegates(self):
        preview = MagicMock()
        preview.prepared.ctx.settings = __import__(
            "spell_sync.runtime_settings",
            fromlist=["RuntimeSettings"],
        ).RuntimeSettings.defaults()
        with (
            patch.object(commands.sys, "stdin") as stdin,
            patch.object(commands, "confirm_chrome_before_push", return_value=True) as chrome,
            patch.object(commands, "confirm_firefox_before_push", return_value=True) as firefox,
        ):
            stdin.isatty.return_value = True
            self.assertTrue(commands._running_apps_check_for_push(DEFAULT_OPTS, preview))
            chrome.assert_called_once_with(interactive=True, settings=preview.prepared.ctx.settings)
            firefox.assert_called_once_with(
                interactive=True,
                settings=preview.prepared.ctx.settings,
            )

    def test_running_apps_check_for_push_yes_skips_prompt(self):
        preview = MagicMock()
        preview.prepared.ctx.settings = __import__(
            "spell_sync.runtime_settings",
            fromlist=["RuntimeSettings"],
        ).RuntimeSettings.defaults()
        with (
            patch.object(commands.sys, "stdin") as stdin,
            patch.object(commands, "confirm_chrome_before_push", return_value=True) as chrome,
            patch.object(commands, "confirm_firefox_before_push", return_value=True) as firefox,
        ):
            stdin.isatty.return_value = True
            self.assertTrue(commands._running_apps_check_for_push(CliOptions(yes=True), preview))
            chrome.assert_called_once_with(
                interactive=False, settings=preview.prepared.ctx.settings
            )
            firefox.assert_called_once_with(
                interactive=False,
                settings=preview.prepared.ctx.settings,
            )

    def test_status_unreadable_json(self):
        run = make_sync_run("/tmp/x", dictionaries=[])
        run.check_wordlist = lambda: ExitCode.WORDLIST_UNREADABLE  # type: ignore
        with patch_commands_service(load_status=status_snapshot_from_run(run)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_status(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))
            self.assertEqual(
                json.loads(buf.getvalue())["exit"],
                int(ExitCode.WORDLIST_UNREADABLE),
            )

    def test_status_warns_destructive_push_risk(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["a"], "utf-8", False, quiet=True)
            write_text_words(
                dict_path,
                [f"w{i}" for i in range(25)],
                "utf-8",
                False,
                quiet=True,
            )
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with patch_commands_service(load_status=status_snapshot_from_run(run)):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_status(DEFAULT_OPTS)
            self.assertEqual(code, 0)
            self.assertIn("run `pull` first", buf.getvalue())

    def test_cmd_init_json(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.getcwd()
            try:
                os.chdir(d)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_init(CliOptions(json_output=True))
                self.assertEqual(code, 0)
                payload = json.loads(buf.getvalue())
                self.assertIn("created", payload)
            finally:
                os.chdir(previous)

    def test_cmd_init_nothing_to_create(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.getcwd()
            try:
                os.chdir(d)
                commands.cmd_init(CliOptions())
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_init(DEFAULT_OPTS)
                self.assertEqual(code, 0)
                self.assertIn("already exist", buf.getvalue())
            finally:
                os.chdir(previous)


class TestLogOutput(unittest.TestCase):
    def test_dictionary_status_and_verbose_diff(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.dictionary_status("macos", 10, 8, 2, 0)
            log.dictionary_word_diff("добавить", tuple(f"w{i}" for i in range(20)))
        out = buf.getvalue()
        self.assertIn("macos:", out)
        self.assertIn("… (+8)", out)

    def test_lint_item_and_note(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.lint_item("detail")
            log.lint_note("note")
        self.assertIn("detail", buf.getvalue())
        self.assertIn("note", buf.getvalue())

    def test_quiet_skips_lint_item_and_note(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.lint_item("hidden")
            log.lint_note("hidden")
        self.assertEqual(buf.getvalue(), "")

    def test_quiet_skips_status_and_lint(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.dictionary_status("x", 1, 1, 0, 0)
            log.lint_group("test", 1)
            log.detail("hidden")
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
