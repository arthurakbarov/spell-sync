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

import spell_sync.commands as commands_mod
import spell_sync.config_check_cmd as config_check_mod
import spell_sync.doctor as doctor_mod
import spell_sync.plan_cmd as plan_mod
import spell_sync.settings as settings_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_run import DictionaryDiff, PushResult


class TestPullPushAliases(unittest.TestCase):
    def test_pull_json_uses_pull_command_name(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            mock_run = MagicMock()
            mock_run.pull_into_wordlist.return_value = (1, 2)
            with patch("spell_sync.commands.sync_run_for", return_value=mock_run):
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
            with (
                patch("spell_sync.commands.sync_run_for") as sync_run_for,
                patch("spell_sync.commands.finish_push", return_value=int(ExitCode.OK)) as finish,
            ):
                sync_run_for.return_value.check_wordlist.return_value = None
                sync_run_for.return_value.plan_push.return_value = fake_result
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
            with patch(
                "spell_sync.doctor.sync_run_for",
                return_value=type(
                    "Run",
                    (),
                    {
                        "wordlist_str": str(Path(d) / "wordlist.txt"),
                        "dictionaries": [
                            Dictionary("demo", str(dict_path), DictionaryFormat.TEXT),
                        ],
                    },
                )(),
            ):
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
            with patch("spell_sync.plan_cmd.sync_run_for") as sync_run_for:
                run = sync_run_for.return_value
                run.check_wordlist.return_value = None
                run.load_wordlist.return_value = {"alpha"}
                run.status_diffs.return_value = []
                run.plan_push.return_value = PushResult(
                    word_count=1,
                    written=("demo",),
                    skipped=(),
                    skipped_reasons={},
                    skipped_details={},
                )
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

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[push]\nstrict = true\nstrict = false\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

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
        with patch("spell_sync.plan_cmd.sync_run_for") as sync_run_for:
            sync_run_for.return_value.check_wordlist.return_value = None
            sync_run_for.return_value.load_wordlist.return_value = {"alpha"}
            sync_run_for.return_value.status_diffs.return_value = []
            sync_run_for.return_value.plan_push.return_value = ExitCode.PUSH_ABORT
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
            with patch(
                "spell_sync.doctor.sync_run_for",
                return_value=type(
                    "Run",
                    (),
                    {
                        "wordlist_str": str(Path(d) / "wordlist.txt"),
                        "dictionaries": [
                            Dictionary("demo", str(dict_path), DictionaryFormat.TEXT),
                        ],
                    },
                )(),
            ):
                code = doctor_mod.cmd_doctor(CliOptions(show_targets=True))
            self.assertEqual(code, int(ExitCode.OK))

    def test_doctor_targets_human_empty(self):
        with patch(
            "spell_sync.doctor.sync_run_for",
            return_value=type(
                "Run",
                (),
                {"wordlist_str": "/tmp/wordlist.txt", "dictionaries": []},
            )(),
        ):
            code = doctor_mod.cmd_doctor(CliOptions(show_targets=True))
        self.assertEqual(code, int(ExitCode.OK))

    def test_plan_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.plan_cmd.sync_run_for") as sync_run_for:
                run = sync_run_for.return_value
                run.check_wordlist.return_value = None
                run.load_wordlist.return_value = {"alpha"}
                run.status_diffs.return_value = [
                    DictionaryDiff(
                        name="demo",
                        target_count=1,
                        local_count=1,
                        to_add=0,
                        to_remove=0,
                        add_words=(),
                        remove_words=(),
                    ),
                ]
                run.plan_push.return_value = PushResult(
                    word_count=1,
                    written=("demo",),
                    skipped=(),
                    skipped_reasons={},
                    skipped_details={},
                )
                code = plan_mod.cmd_plan(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_plan_wordlist_error(self):
        with patch("spell_sync.plan_cmd.sync_run_for") as sync_run_for:
            sync_run_for.return_value.check_wordlist.return_value = ExitCode.WORDLIST_UNREADABLE
            code = plan_mod.cmd_plan(CliOptions())
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
                "spell_sync.command_helpers.acquire_operation_lock",
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
                "spell_sync.command_helpers.acquire_operation_lock",
                side_effect=OperationLocked(info, lock_path),
            ):
                code = commands_mod.cmd_push(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
