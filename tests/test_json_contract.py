"""JSON output contract: always includes `command` and `exit`."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from service_test_utils import (
    doctor_targets_from_run,
    executable_push_preview,
    patch_commands_service,
    patch_doctor_service,
    patch_plan_service,
    pull_execution,
    pull_preview_executable,
    push_execution,
    status_snapshot_from_run,
)

import spell_sync.commands as commands
import spell_sync.doctor as doctor_mod
import spell_sync.plan_cmd as plan_mod
from spell_sync.application import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from tests.runtime_helpers import make_sync_run


class TestJsonContract(unittest.TestCase):
    def _assert_has_exit(self, payload: dict[str, object]) -> None:
        self.assertIn("command", payload)
        self.assertIn("exit", payload)
        self.assertIn("schema_version", payload)
        self.assertEqual(payload["schema_version"], 1)

    def test_status_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertIn("warnings", payload)
            self.assertIsInstance(payload["warnings"], list)

    def test_status_json_missing_wordlist_is_not_empty(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertEqual(payload["exit"], int(ExitCode.WORDLIST_UNREADABLE))

    def test_status_json_includes_git_dirty_warning(self):
        import subprocess
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=str(root),
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(root),
                check=True,
                capture_output=True,
            )
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\nsublime = true\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "add", "wordlist.txt", "spell-sync.toml"],
                cwd=str(root),
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=str(root),
                check=True,
                capture_output=True,
            )
            wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
            run = make_sync_run(str(wordlist), dictionaries=[])
            buf = io.StringIO()
            with (
                patch_commands_service(load_status=status_snapshot_from_run(run)),
                redirect_stdout(buf),
            ):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=str(wordlist)))
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(
                any("uncommitted changes" in warning for warning in payload["warnings"]),
                payload["warnings"],
            )

    def test_status_json_includes_empty_wordlist_warning(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("", encoding="utf-8")
            run = make_sync_run(wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch_commands_service(load_status=status_snapshot_from_run(run)),
                redirect_stdout(buf),
            ):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(
                any("word list is empty" in warning for warning in payload["warnings"]),
                payload["warnings"],
            )

    def test_pull_json_includes_warnings_key(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            preview = pull_preview_executable(wordlist, 1, 1)
            execution = pull_execution(1, 1, preview=preview)
            buf = io.StringIO()
            with (
                patch_commands_service(
                    prepare_pull=preview,
                    execute_pull=execution,
                    build_pull_report=MagicMock(),
                ),
                redirect_stdout(buf),
            ):
                code = commands.cmd_pull(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("warnings", payload)
            self.assertIsInstance(payload["warnings"], list)

    def test_status_json_is_pure_with_corrupt_jetbrains_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            bad_xml = os.path.join(d, "cachedDictionary.xml")
            with open(bad_xml, "w", encoding="utf-8") as handle:
                handle.write("not xml")
            run = make_sync_run(
                wordlist,
                dictionaries=[
                    Dictionary(
                        "jetbrains:IDEA",
                        bad_xml,
                        DictionaryFormat.JETBRAINS,
                    )
                ],
            )
            buf = io.StringIO()
            with (
                patch_commands_service(load_status=status_snapshot_from_run(run)),
                redirect_stdout(buf),
            ):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            self._assert_has_exit(json.loads(out))

    def test_doctor_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = doctor_mod.cmd_doctor(CliOptions(json_output=True, wordlist=wordlist))
            self.assertIn(code, (0, 1))
            self._assert_has_exit(json.loads(buf.getvalue()))

    def test_doctor_check_json_has_health_fields(self):
        import spell_sync.health.report as report_mod

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = make_sync_run(wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch.object(
                    doctor_mod._SERVICE,
                    "load_doctor_report",
                    return_value=doctor_mod.build_doctor_report(run),
                ),
                patch.object(
                    report_mod,
                    "inspect_cli",
                    return_value=doctor_mod.CliStatus(
                        on_path=True,
                        argv=("/usr/bin/spell-sync",),
                        executable="/usr/bin/spell-sync",
                        pip_script=None,
                        path_export=None,
                    ),
                ),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(
                    CliOptions(json_output=True, health_check=True, wordlist=wordlist),
                )
            self.assertEqual(code, int(ExitCode.OK))
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertTrue(payload["ok"])
            self.assertIn("action_count", payload)
            self.assertIn("required_action_count", payload)
            self.assertIn("actions", payload)

    def test_doctor_targets_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = make_sync_run(wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch_doctor_service(load_doctor_targets=doctor_targets_from_run(run)),
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(
                    CliOptions(json_output=True, show_targets=True, wordlist=wordlist),
                )
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertTrue(payload["targets"])

    def test_lint_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_lint(CliOptions(json_output=True, wordlist=wordlist))
            self.assertIn(code, (0, 2))
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            self._assert_has_exit(json.loads(out))

    def test_plan_removals_json_is_pure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            preview = executable_push_preview()
            with (
                patch_plan_service(load_push_preview=preview),
                redirect_stdout(buf := io.StringIO()),
            ):
                code = plan_mod.cmd_plan(
                    CliOptions(json_output=True, plan_removals=True, wordlist=wordlist),
                )
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            payload = json.loads(out)
            self._assert_has_exit(payload)
            self.assertEqual(payload["command"], "plan")
            self.assertTrue(payload["removals"])

    def test_push_cancel_json_is_pure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            preview = executable_push_preview()
            buf = io.StringIO()
            with (
                patch_commands_service(load_push_preview=preview),
                patch.object(commands, "log_skipped_optional_app_details"),
                patch.object(commands, "_running_apps_check_for_push", return_value=False),
                redirect_stdout(buf),
            ):
                code = commands.cmd_push(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.CANCELLED))
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            payload = json.loads(out)
            self._assert_has_exit(payload)
            self.assertEqual(payload["command"], "push")
            self.assertEqual(payload["exit"], int(ExitCode.CANCELLED))
            self.assertEqual(payload["action"], "cancelled")
            self.assertEqual(payload["reason"], "running_apps_check")

    def test_push_json_does_not_prompt_in_tty(self):
        preview = executable_push_preview()
        execution = push_execution(ExitCode.OK, preview=preview)
        buf = io.StringIO()
        with (
            patch_commands_service(
                load_push_preview=preview,
                execute_push_preview=execution,
                build_push_report=MagicMock(),
            ),
            patch.object(commands, "log_skipped_optional_app_details"),
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
            patch.object(commands, "review_removals_for_preview", return_value=True),
            patch.object(commands.sys, "stdin") as stdin,
            patch("builtins.input", side_effect=AssertionError("must not prompt")),
            redirect_stdout(buf),
        ):
            stdin.isatty.return_value = True
            code = commands.cmd_push(CliOptions(json_output=True, review_removals=True))
        self.assertIn(code, (0, 1, 4, 130))


class TestJsonContractExtended(unittest.TestCase):
    def _assert_json_stdout(self, buf: io.StringIO) -> dict[str, object]:
        out = buf.getvalue()
        self.assertTrue(out.lstrip().startswith("{"))
        payload = json.loads(out)
        self.assertIn("command", payload)
        self.assertIn("exit", payload)
        return payload

    def test_init_json_has_exit(self):
        buf = io.StringIO()
        with (
            patch.object(
                SpellSyncService,
                "execute_project_setup",
                return_value=MagicMock(
                    outcome=MagicMock(value="completed"),
                    created_files=("wordlist.txt",),
                ),
            ),
            patch.object(
                SpellSyncService,
                "prepare_project_setup",
                return_value=MagicMock(setup_id="setup-1"),
            ),
            redirect_stdout(buf),
        ):
            code = commands.cmd_init(CliOptions(json_output=True))
        self.assertEqual(code, 0)
        payload = self._assert_json_stdout(buf)
        self.assertEqual(payload["command"], "init")

    def test_pull_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            preview = pull_preview_executable(wordlist, 1, 1)
            execution = pull_execution(1, 1, preview=preview)
            buf = io.StringIO()
            with (
                patch_commands_service(
                    prepare_pull=preview,
                    execute_pull=execution,
                    build_pull_report=MagicMock(),
                ),
                redirect_stdout(buf),
            ):
                code = commands.cmd_pull(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            payload = self._assert_json_stdout(buf)
            self.assertEqual(payload["command"], "pull")


if __name__ == "__main__":
    unittest.main(verbosity=2)
