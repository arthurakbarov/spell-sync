"""app_process_check tests and push/sync integration."""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from service_test_utils import (
    executable_push_preview,
    patch_commands_service,
    patch_isolated_push,
    status_snapshot_from_run,
)

import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.runtime_settings import RuntimeSettings
from tests.runtime_helpers import make_sync_run

_SETTINGS = RuntimeSettings.defaults()


class TestChromeCheck(unittest.TestCase):
    def test_skips_when_chrome_disabled(self):
        import spell_sync.app_process_check as guard

        with patch.object(guard, "chrome_dictionaries_enabled", return_value=False):
            self.assertTrue(guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS))

    def test_skips_when_chrome_not_running(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=False),
        ):
            self.assertTrue(guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS))

    def test_non_interactive_warns_and_proceeds(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=True),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(
                    guard.confirm_chrome_before_push(interactive=False, settings=_SETTINGS)
                )
            self.assertIn("Chrome is running", buf.getvalue())

    def test_interactive_cancel(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            self.assertFalse(guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS))

    def test_unknown_chrome_state_warns(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=None),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(
                    guard.confirm_chrome_before_push(interactive=False, settings=_SETTINGS)
                )
            self.assertIn("Could not check", buf.getvalue())

    def test_pgrep_error_returns_unknown(self):
        import spell_sync.app_process_check as guard

        fake_result = type("R", (), {"returncode": 2})()
        with patch.object(guard.subprocess, "run", return_value=fake_result):
            self.assertIsNone(guard._macos_pgrep_exact("Google Chrome"))

    def test_pgrep_running_true_and_false(self):
        import spell_sync.app_process_check as guard

        self.assertTrue(guard._pgrep_running(0))
        self.assertFalse(guard._pgrep_running(1))
        self.assertIsNone(guard._pgrep_running(2))

    def test_macos_pgrep_first_running_all_not_found(self):
        import spell_sync.app_process_check as guard

        fake_result = type("R", (), {"returncode": 1})()
        with patch.object(guard.subprocess, "run", return_value=fake_result):
            self.assertFalse(guard._macos_pgrep_first_running("Google Chrome", "Chromium"))

    def test_chrome_dictionaries_disabled_without_paths(self):
        import spell_sync.app_process_check as guard

        with (
            patch("spell_sync.config.enable_chrome", return_value=True),
            patch.object(guard, "chrome_dict_paths", return_value=[]),
        ):
            self.assertFalse(guard.chrome_dictionaries_enabled(settings=_SETTINGS))

    def test_interactive_yes(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            self.assertTrue(guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS))

    def test_interactive_eof_returns_none(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=True),
            patch("builtins.input", side_effect=EOFError),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertIsNone(
                    guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS)
                )
            self.assertIn("Cancelled", buf.getvalue())

    def test_interactive_keyboard_interrupt_returns_none(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=None),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            self.assertIsNone(
                guard.confirm_chrome_before_push(interactive=True, settings=_SETTINGS),
            )

    def test_is_chrome_running_windows(self):
        import spell_sync.app_process_check as guard

        fake = type("R", (), {"returncode": 0, "stdout": "chrome.exe 1234"})()
        with (
            patch.object(guard, "is_windows", return_value=True),
            patch.object(guard.subprocess, "run", return_value=fake),
        ):
            self.assertTrue(guard.is_chrome_running())

    def test_is_chrome_running_linux_pgrep(self):
        import spell_sync.app_process_check as guard

        fake = type("R", (), {"returncode": 0})()
        with (
            patch.object(guard, "is_windows", return_value=False),
            patch.object(guard.sys, "platform", "linux"),
            patch.object(guard.subprocess, "run", return_value=fake),
        ):
            self.assertTrue(guard.is_chrome_running())

    def test_chrome_running_macos_os_error(self):
        import spell_sync.app_process_check as guard

        with patch.object(
            guard.subprocess,
            "run",
            side_effect=OSError("pgrep missing"),
        ):
            self.assertIsNone(guard._macos_pgrep_exact("Google Chrome"))

    def test_chrome_running_windows_tasklist_failure(self):
        import spell_sync.app_process_check as guard

        fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom" * 300})()
        with patch.object(guard.subprocess, "run", return_value=fake):
            self.assertIsNone(guard._windows_exe_running("chrome.exe"))

    def test_chrome_running_windows_os_error(self):
        import spell_sync.app_process_check as guard

        with patch.object(
            guard.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("tasklist", 10),
        ):
            self.assertIsNone(guard._windows_exe_running("chrome.exe"))

    def test_chrome_running_linux_not_found(self):
        import spell_sync.app_process_check as guard

        fake = type("R", (), {"returncode": 1})()
        with patch.object(guard.subprocess, "run", return_value=fake):
            self.assertFalse(
                guard._linux_pgrep_first_resolved(
                    "chrome",
                    "google-chrome",
                    "google-chrome-stable",
                )
            )

    def test_chrome_running_linux_tries_alternate_process_names(self):
        import spell_sync.app_process_check as guard

        def fake_run(cmd, **kwargs):
            name = cmd[-1]
            rc = 0 if name == "google-chrome" else 1
            return type("R", (), {"returncode": rc})()

        with patch.object(guard.subprocess, "run", side_effect=fake_run):
            self.assertTrue(
                guard._linux_pgrep_first_resolved(
                    "chrome",
                    "google-chrome",
                    "google-chrome-stable",
                )
            )

    def test_firefox_running_linux_tries_firefox_esr(self):
        import spell_sync.app_process_check as guard

        def fake_run(cmd, **kwargs):
            name = cmd[-1]
            rc = 0 if name == "firefox-esr" else 1
            return type("R", (), {"returncode": rc})()

        with (
            patch.object(guard, "is_windows", return_value=False),
            patch.object(guard.sys, "platform", "linux"),
            patch.object(guard.subprocess, "run", side_effect=fake_run),
        ):
            self.assertTrue(guard.is_firefox_running())

    def test_is_chrome_running_dispatches_to_macos(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "is_windows", return_value=False),
            patch.object(guard.sys, "platform", "darwin"),
            patch.object(guard, "_macos_pgrep_exact", return_value=True) as mac,
        ):
            self.assertTrue(guard.is_chrome_running())
            mac.assert_called_once_with("Google Chrome")

    def test_chrome_running_linux_unknown_pgrep(self):
        import spell_sync.app_process_check as guard

        fake = type("R", (), {"returncode": 2})()
        with patch.object(guard.subprocess, "run", return_value=fake):
            self.assertIsNone(
                guard._linux_pgrep_first_resolved(
                    "chrome",
                    "google-chrome",
                    "google-chrome-stable",
                )
            )

    def test_chrome_running_linux_os_error(self):
        import spell_sync.app_process_check as guard

        with patch.object(
            guard.subprocess,
            "run",
            side_effect=OSError("pgrep missing"),
        ):
            self.assertIsNone(
                guard._linux_pgrep_first_resolved(
                    "chrome",
                    "google-chrome",
                    "google-chrome-stable",
                )
            )

    def test_chrome_running_linux_os_error_then_found(self):
        import spell_sync.app_process_check as guard

        def fake_run(cmd, **kwargs):
            name = cmd[-1]
            if name == "chrome":
                raise OSError("transient")
            return type("R", (), {"returncode": 0})()

        with patch.object(guard.subprocess, "run", side_effect=fake_run):
            self.assertTrue(
                guard._linux_pgrep_first_resolved(
                    "chrome",
                    "google-chrome",
                    "google-chrome-stable",
                )
            )

    def test_macos_pgrep_first_running_unknown_then_false(self):
        import spell_sync.app_process_check as guard

        def fake_run(cmd, **kwargs):
            name = cmd[-1]
            rc = 2 if name == "firefox" else 1
            return type("R", (), {"returncode": rc})()

        with patch.object(guard.subprocess, "run", side_effect=fake_run):
            self.assertIsNone(guard._macos_pgrep_first_running("firefox", "Firefox"))


class TestPushChromeGuard(unittest.TestCase):
    def test_cmd_push_cancelled_when_running_apps_check_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            preview = executable_push_preview()
            with (
                patch_commands_service(load_push_preview=preview),
                patch.object(commands, "log_skipped_optional_app_details"),
                patch.object(commands, "_running_apps_check_for_push", return_value=False),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(
                        commands.cmd_push(CliOptions(wordlist=wordlist)),
                        int(ExitCode.CANCELLED),
                    )

    def test_cmd_push_runs_when_guard_ok(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist, dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)]
            )
            with patch_isolated_push(run):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        commands.cmd_push(CliOptions(wordlist=wordlist, yes=True)),
                        0,
                    )
                self.assertEqual(read_text_words(dict_path, quiet=True), {"alpha"})

    def test_cmd_push_yes_skips_chrome_prompt(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "chrome_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_chrome_running", return_value=True),
            patch("builtins.input", side_effect=AssertionError("should not prompt")),
        ):
            with tempfile.TemporaryDirectory() as d:
                wordlist = os.path.join(d, "wordlist.txt")
                dict_path = os.path.join(d, "a.txt")
                write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
                write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
                run = make_sync_run(
                    wordlist, dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)]
                )
                with patch_isolated_push(run):
                    with patch.object(commands.sys, "stdin") as stdin:
                        stdin.isatty.return_value = True
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(
                                commands.cmd_push(CliOptions(wordlist=wordlist, yes=True)),
                                0,
                            )


class TestChromeGuard(unittest.TestCase):
    def test_cmd_status_empty_wordlist_warns(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            open(wordlist, "w", encoding="utf-8").close()
            write_text_words(dict_path, ["beta"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist, dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)]
            )
            snapshot = status_snapshot_from_run(run)
            with patch_commands_service(load_status=snapshot):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    commands.cmd_status(CliOptions(wordlist=wordlist))
                self.assertIn("word list is empty", buf.getvalue())

    def test_cmd_push_empty_wordlist_aborts(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            open(wordlist, "w", encoding="utf-8").close()
            write_text_words(dict_path, ["beta"], "utf-8", False, quiet=True)
            with (
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=True,
                ),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(wordlist=wordlist))
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                self.assertEqual(read_text_words(dict_path, quiet=True), {"beta"})
                self.assertIn("word list is empty", buf.getvalue())

    def test_cmd_push_write_failure_does_not_claim_empty_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist, dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)]
            )
            with (
                patch_isolated_push(run),
                patch("spell_sync.push_prepared.write_rendered", return_value=False),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(wordlist=wordlist, yes=True))
                out = buf.getvalue()
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                self.assertIn("not written", out)
                self.assertNotIn("wordlist is empty", out)


class TestEdgeProcessCheck(unittest.TestCase):
    def test_edge_confirm_skips_when_disabled(self):
        import spell_sync.app_process_check as guard

        with patch.object(guard, "edge_dictionaries_enabled", return_value=False):
            self.assertTrue(guard.confirm_edge_before_push(interactive=True, settings=_SETTINGS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
