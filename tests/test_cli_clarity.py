#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI clarity: pull/push aliases, plan, targets, config check."""

from __future__ import annotations

import io
import json
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
    push_plan_tuple,
    status_snapshot_from_run,
)

import spell_sync.commands as commands_mod
import spell_sync.config_check_cmd as config_check_mod
import spell_sync.doctor as doctor_mod
import spell_sync.plan_cmd as plan_mod
import spell_sync.settings as settings_mod
from spell_sync.application.reports import PushPreview, StatusSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_run import PushResult
from tests.runtime_helpers import make_sync_run


class TestPullPushAliases(unittest.TestCase):
    def test_pull_json_uses_pull_command_name(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            preview = pull_preview_executable(str(wordlist), 1, 2)
            execution = pull_execution(1, 2, preview=preview)
            with patch_commands_service(
                prepare_pull=preview,
                execute_pull=execution,
                build_pull_report=MagicMock(),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands_mod.cmd_pull(
                        CliOptions(wordlist=str(wordlist), json_output=True),
                    )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(payload["command"], "pull")

    def test_push_delegates_to_push_with_command_name(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            fake_result = PushResult(
                word_count=1,
                written=(),
                skipped=(),
                skipped_reasons={},
                skipped_details={},
            )
            preview = executable_push_preview()
            execution = push_execution(fake_result, preview=preview)
            with (
                patch_commands_service(
                    load_push_preview=preview,
                    execute_push_dry_run=execution,
                    load_status=StatusSnapshot(
                        wordlist_count=1,
                        diffs=(),
                        skipped_unreadable=(),
                        skipped_corrupt=(),
                    ),
                ),
                patch("spell_sync.commands.finish_push", return_value=int(ExitCode.OK)) as finish,
            ):
                code = commands_mod.cmd_push(
                    CliOptions(wordlist=str(wordlist), dry_run=True, yes=True),
                )
            finish.assert_called_once()
            self.assertEqual(finish.call_args.kwargs["command"], "push")
            self.assertEqual(code, int(ExitCode.OK))


class TestConfigCheck(unittest.TestCase):
    def test_config_check_ok_json(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = config_check_mod.cmd_config_check(CliOptions(json_output=True))
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "config-check")

    def test_config_check_unknown_key_fails(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nunknown = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                code = config_check_mod.cmd_config_check(CliOptions())
            self.assertEqual(code, int(ExitCode.LINT_FAILED))


class TestDoctorTargets(unittest.TestCase):
    def test_doctor_targets_json_lists_discovered_paths(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = Path(d) / "dict.txt"
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(
                str(Path(d) / "wordlist.txt"),
                dictionaries=[Dictionary("demo", str(dict_path), DictionaryFormat.TEXT)],
            )
            with patch_doctor_service(load_doctor_targets=doctor_targets_from_run(run)):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = doctor_mod.cmd_doctor(
                        CliOptions(json_output=True, show_targets=True),
                    )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(payload["command"], "doctor")
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["targets_list"][0]["name"], "demo")


class TestPlan(unittest.TestCase):
    def test_plan_json_preview(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(str(wordlist), dictionaries=[])
            result = PushResult(
                word_count=1,
                written=("demo",),
                skipped=(),
                skipped_reasons={},
                skipped_details={},
            )
            plan = push_plan_tuple(run, result)
            with patch_plan_service(
                load_push_plan=plan,
                load_status=status_snapshot_from_run(run),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = plan_mod.cmd_plan(CliOptions(wordlist=str(wordlist), json_output=True))
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(payload["command"], "plan")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["written"], ["demo"])


class TestTomllibParser(unittest.TestCase):
    def test_standard_toml_bool(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[push]\nstrict = true\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(issues, [])
            self.assertTrue(data["push"]["strict"])

    def test_accepts_integers(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[io]\nbackup_keep = 3\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(issues, [])
            self.assertEqual(data["io"]["backup_keep"], 3)

    def test_scalar_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text('title = "spell-sync"\n[push]\nstrict = true\n', encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertTrue(data.get("push", {}).get("strict"))
            self.assertTrue(any("must be a table" in issue for issue in issues))

    def test_read_oserror_and_decode_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[push]\nstrict = true\n", encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=OSError("nope")):
                data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)
            path.write_text("[[[broken", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_rejects_string_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text('[push]\nname = "spell-sync"\n', encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(any("unsupported value type" in issue for issue in issues))

    def test_loads_receives_str_not_bytes(self):
        seen: list[object] = []

        def fake_loads(raw: object):
            seen.append(raw)
            return {"push": {"strict": True}}

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[push]\nstrict = true\n", encoding="utf-8")
            with patch.object(settings_mod.tomllib, "loads", side_effect=fake_loads):
                data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(issues, [])
            self.assertTrue(data["push"]["strict"])
            self.assertEqual(len(seen), 1)
            self.assertIsInstance(seen[0], str)


class TestStage3HumanOutput(unittest.TestCase):
    def test_config_check_human_ok(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                code = config_check_mod.cmd_config_check(CliOptions())
            self.assertEqual(code, int(ExitCode.OK))

    def test_plan_json_abort(self):
        run = make_sync_run("/tmp/x", dictionaries=[])
        plan = push_plan_tuple(run, ExitCode.PUSH_ABORT)
        with patch_plan_service(
            load_push_plan=plan,
            load_status=status_snapshot_from_run(run),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = plan_mod.cmd_plan(CliOptions(json_output=True))
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertEqual(payload["exit"], int(ExitCode.PUSH_ABORT))

    def test_config_check_human_no_config_files(self):
        with patch.object(settings_mod, "config_paths", return_value=[]):
            code = config_check_mod.cmd_config_check(CliOptions())
        self.assertEqual(code, int(ExitCode.OK))

    def test_config_check_human_parse_issues(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("orphan = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                code = config_check_mod.cmd_config_check(CliOptions())
            self.assertEqual(code, int(ExitCode.LINT_FAILED))

    def test_doctor_targets_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = Path(d) / "dict.txt"
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(
                str(Path(d) / "wordlist.txt"),
                dictionaries=[Dictionary("demo", str(dict_path), DictionaryFormat.TEXT)],
            )
            with patch_doctor_service(load_doctor_targets=doctor_targets_from_run(run)):
                code = doctor_mod.cmd_doctor(CliOptions(show_targets=True))
            self.assertEqual(code, int(ExitCode.OK))

    def test_doctor_targets_human_empty(self):
        run = make_sync_run("/tmp/wordlist.txt", dictionaries=[])
        with patch_doctor_service(load_doctor_targets=doctor_targets_from_run(run)):
            code = doctor_mod.cmd_doctor(CliOptions(show_targets=True))
        self.assertEqual(code, int(ExitCode.OK))

    def test_plan_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("demo", str(wordlist), DictionaryFormat.TEXT)],
            )
            result = PushResult(
                word_count=1,
                written=("demo",),
                skipped=(),
                skipped_reasons={},
                skipped_details={},
            )
            plan = push_plan_tuple(
                run,
                result,
                verbose=False,
            )
            with patch_plan_service(
                load_push_plan=plan,
                load_status=status_snapshot_from_run(run),
            ):
                code = plan_mod.cmd_plan(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_plan_wordlist_error(self):
        preview = executable_push_preview()
        preview = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="2026-01-01T00:00:00+00:00",
            plan_identifier="blocked",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            wordlist_error=ExitCode.WORDLIST_UNREADABLE,
        )
        with patch_plan_service(load_push_preview=preview):
            code = plan_mod.cmd_plan(CliOptions(plan_removals=True))
        self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))

    def test_pull_lock_exit(self):
        from spell_sync.operation_lock import (
            OperationLocked,
            OperationLockInfo,
            lock_path_for_wordlist,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            info = OperationLockInfo(1, "2026-01-01T00:00:00+00:00", "pull", str(wordlist))
            lock_path = lock_path_for_wordlist(wordlist)
            with patch(
                "spell_sync.mutation_guards.acquire_operation_lock",
                side_effect=OperationLocked(info, lock_path),
            ):
                code = commands_mod.cmd_pull(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_push_lock_exit(self):
        from spell_sync.operation_lock import (
            OperationLocked,
            OperationLockInfo,
            lock_path_for_wordlist,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            info = OperationLockInfo(1, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
            lock_path = lock_path_for_wordlist(wordlist)
            with patch(
                "spell_sync.mutation_guards.acquire_operation_lock",
                side_effect=OperationLocked(info, lock_path),
            ):
                code = commands_mod.cmd_push(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
