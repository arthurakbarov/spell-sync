#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structural invariants and cross-cutting contracts.

These guard refactors (CLI wiring, stable exit codes, skip-reason maps) and
multi-dictionary push logic. They are not a substitute for line coverage —
CI enforces that separately.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from dataclasses import replace
from typing import Iterable

from support.wiring import cli_subcommand_names

import spell_sync.cli as cli_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.health.serialize import (
    doctor_action_payload,
    doctor_command_payload,
    doctor_payload,
    doctor_report_exit_code,
    git_hooks_payload,
)
from spell_sync.health.types import (
    CliStatus,
    DoctorAction,
    DoctorCheck,
    DoctorReport,
    GitHooksStatus,
    format_action_line,
)
from spell_sync.io import write_text_words
from spell_sync.json_output import push_result_payload
from spell_sync.skip_reasons import PUSH_SKIP_DETAILS, PushSkipReason
from spell_sync.sync_run import PushResult, SyncRun
from spell_sync.words import merge_case_duplicates


def _skip_reason_constants(cls: type) -> set[str]:
    return {
        value
        for name, value in vars(cls).items()
        if not name.startswith("_") and isinstance(value, str)
    }


def _push_skip_reason_constants() -> set[str]:
    return _skip_reason_constants(PushSkipReason)


class TestDoctorPayloadInvariants(unittest.TestCase):
    REQUIRED_KEYS = {
        "wordlist_path",
        "wordlist_count",
        "version",
        "skipped_unreadable",
        "git_hooks",
        "cli",
        "dictionaries_total",
        "dictionaries_readable",
        "dictionaries_writable",
        "max_drift_add",
        "max_drift_remove",
        "actions",
        "required_action_count",
        "checks",
    }

    CLI_KEYS = {"on_path", "argv", "executable", "pip_script", "path_export", "command_prefix"}

    def test_doctor_payload_has_required_keys(self):
        report = DoctorReport(
            wordlist_path="/tmp/wordlist.txt",
            wordlist_count=1,
            package_version="0.0.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=CliStatus(
                on_path=True,
                argv=("spell-sync",),
                executable="/usr/bin/spell-sync",
                pip_script=None,
                path_export=None,
            ),
            actions=(),
            checks=(),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        payload = doctor_payload(report)
        self.assertEqual(set(payload), self.REQUIRED_KEYS)
        self.assertEqual(set(payload["cli"]), self.CLI_KEYS)
        self.assertIsInstance(payload["actions"], list)
        self.assertIsInstance(payload["required_action_count"], int)

    def test_git_hooks_payload_shape(self):
        status = GitHooksStatus(
            pre_push=False,
            pre_commit=True,
            pre_push_stale=False,
        )
        payload = git_hooks_payload(status)
        assert payload is not None
        self.assertEqual(
            set(payload),
            {"pre_push", "pre_commit", "pre_push_stale"},
        )
        self.assertIsNone(git_hooks_payload(None))

    def test_doctor_action_payload_omits_empty_fields(self):
        required = doctor_action_payload(
            DoctorAction(id="upgrade-tool", reason="outdated", command="scripts/sync-tool.sh"),
        )
        self.assertEqual(set(required), {"id", "reason", "optional", "command"})
        optional = doctor_action_payload(
            DoctorAction(
                id="macos-fda",
                reason="unreadable",
                hint="System Settings",
                optional=True,
            ),
        )
        self.assertTrue(optional["optional"])
        self.assertNotIn("command", optional)
        self.assertIn("hint", optional)

    def test_format_action_line_shell_and_hint(self):
        shell = format_action_line(
            DoctorAction(id="path-fix", reason="missing", shell='export PATH="/tmp/bin:$PATH"'),
        )
        self.assertIn("export PATH", shell)
        hint = format_action_line(
            DoctorAction(id="macos-fda", reason="unreadable", hint="System Settings"),
        )
        self.assertIn("System Settings", hint)
        bare = format_action_line(DoctorAction(id="check", reason="review logs"))
        self.assertEqual(bare, "check: review logs")

    def test_doctor_report_exit_code_health_check(self):
        clean = DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="1.0.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=CliStatus(True, ("spell-sync",), "/usr/bin/spell-sync", None, None),
            actions=(),
            checks=(),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        self.assertEqual(
            int(doctor_report_exit_code(clean, health_check=True)),
            int(ExitCode.OK),
        )
        required_action = DoctorAction(id="upgrade-tool", reason="outdated")
        with_action = replace(clean, actions=(required_action,))
        self.assertEqual(
            int(doctor_report_exit_code(with_action, health_check=True)),
            int(ExitCode.LINT_FAILED),
        )
        with_error = replace(clean, checks=(DoctorCheck("error", "broken"),))
        self.assertEqual(
            int(doctor_report_exit_code(with_error, health_check=True)),
            int(ExitCode.PUSH_ABORT),
        )

    def test_doctor_command_payload_health_check_keys(self):
        report = DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="1.0.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=CliStatus(True, ("spell-sync",), "/usr/bin/spell-sync", None, None),
            actions=(
                DoctorAction(id="recover-push", reason="unfinished journal"),
                DoctorAction(id="macos-fda", reason="fda", optional=True),
            ),
            checks=(),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        payload = doctor_command_payload(report, health_check=True)
        self.assertIn("ok", payload)
        self.assertIn("action_count", payload)
        self.assertEqual(payload["action_count"], 2)
        self.assertEqual(payload["required_action_count"], 1)
        self.assertFalse(payload["ok"])


class TestCliWiringInvariants(unittest.TestCase):
    EXPECTED_COMMANDS = {
        "config-check",
        "doctor",
        "init",
        "lint",
        "plan",
        "pull",
        "push",
        "recover",
        "status",
        "version",
    }

    def test_commands_match_argparse_subparsers(self):
        self.assertEqual(set(cli_mod.COMMANDS), self.EXPECTED_COMMANDS)
        self.assertEqual(set(cli_mod.COMMANDS), cli_subcommand_names())

    def test_every_command_handler_is_callable(self):
        for name, handler in cli_mod.COMMANDS.items():
            self.assertTrue(callable(handler), msg=f"{name} handler is not callable")
            sig = inspect.signature(handler)
            self.assertGreaterEqual(
                len(sig.parameters),
                1,
                msg=f"{name} handler must accept CliOptions",
            )


class TestExitCodeStability(unittest.TestCase):
    """Automation scripts depend on these numeric values."""

    EXPECTED = {
        "OK": 0,
        "PUSH_ABORT": 1,
        "LINT_FAILED": 2,
        "UNKNOWN_COMMAND": 3,
        "CANCELLED": 4,
        "PARTIAL_PUSH": 5,
        "WORDLIST_UNREADABLE": 6,
        "SYNC_INTERRUPTED": 130,
    }

    def test_exit_code_values_are_stable(self):
        for name, value in self.EXPECTED.items():
            self.assertEqual(int(getattr(ExitCode, name)), value)

    def test_exit_code_members_are_unique(self):
        values = [int(member) for member in ExitCode]
        self.assertEqual(len(values), len(set(values)))


class TestSkipReasonInvariants(unittest.TestCase):
    def test_push_skip_details_keys_are_known_reasons(self):
        known = _push_skip_reason_constants()
        for reason in PUSH_SKIP_DETAILS:
            self.assertIn(reason, known)

    def test_push_skip_details_values_are_non_empty(self):
        for reason, detail in PUSH_SKIP_DETAILS.items():
            self.assertTrue(detail.strip(), msg=f"empty detail for {reason!r}")


class TestJsonPayloadInvariants(unittest.TestCase):
    REQUIRED_PUSH_KEYS = {
        "word_count",
        "written",
        "skipped",
        "skipped_reasons",
        "skipped_details",
    }

    def test_push_result_payload_has_required_keys(self):
        result = PushResult(0, (), (), {}, {})
        payload = push_result_payload(result)
        self.assertEqual(set(payload), self.REQUIRED_PUSH_KEYS)

    def test_push_result_payload_lists_are_serializable(self):
        result = PushResult(
            2,
            ("a",),
            ("b",),
            {"b": PushSkipReason.UNREADABLE},
            {"b": "no access — push skipped"},
        )
        payload = push_result_payload(result)
        self.assertEqual(payload["written"], ["a"])
        self.assertEqual(payload["skipped"], ["b"])


class TestDictionaryFormatInvariants(unittest.TestCase):
    SAMPLE = {"alpha", "Beta", "слово"}

    def _roundtrip(self, dictionary: Dictionary) -> set[str]:
        self.assertTrue(dictionary.write(self.SAMPLE, quiet=True))
        return dictionary.read(quiet=True)

    def test_all_dictionary_formats_roundtrip_via_dictionary_class(self):
        cases: Iterable[tuple[DictionaryFormat, str, dict[str, object]]] = (
            (DictionaryFormat.TEXT, "dict.txt", {}),
            (DictionaryFormat.JSON, "prefs.json", {}),
            (DictionaryFormat.CHROME, "Custom Dictionary.txt", {}),
            (DictionaryFormat.HUNSPELL, "custom.dic", {}),
            (DictionaryFormat.JETBRAINS, "cachedDictionary.xml", {}),
        )
        with tempfile.TemporaryDirectory() as d:
            for fmt, filename, extra in cases:
                path = os.path.join(d, filename)
                dictionary = Dictionary(f"fmt-{fmt.value}", path, fmt, **extra)
                with self.subTest(format=fmt.value):
                    self.assertEqual(self._roundtrip(dictionary), self.SAMPLE)


class TestWordMergeInvariants(unittest.TestCase):
    def test_merge_case_duplicates_is_idempotent(self):
        source = ["Alpha", "alpha", "beta", " ", "!!!", "Beta"]
        once = merge_case_duplicates(source)
        twice = merge_case_duplicates(once)
        self.assertEqual(once, twice)

    def test_merge_case_duplicates_preserves_first_seen_casing(self):
        self.assertEqual(merge_case_duplicates(["zebra", "Zebra", "ZEBRA"]), ["zebra"])


class TestPushPlanInvariants(unittest.TestCase):
    def test_plan_push_partitions_dictionaries_without_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_skip = os.path.join(d, "skip.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_skip, ["other"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                    Dictionary("skip", path_skip, DictionaryFormat.TEXT),
                ],
            )
            result = run.plan_push(skip_names=frozenset({"skip"}))
            self.assertIsInstance(result, PushResult)
            assert isinstance(result, PushResult)
            written = set(result.written)
            skipped = set(result.skipped)
            self.assertEqual(written & skipped, set())
            self.assertEqual(written | skipped, {d.name for d in run.dictionaries})

    def test_skipped_reason_keys_are_subset_of_skipped_names(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_skip = os.path.join(d, "skip.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_skip, ["other"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                    Dictionary("skip", path_skip, DictionaryFormat.TEXT),
                ],
            )
            result = run.plan_push(skip_names=frozenset({"skip"}))
            assert isinstance(result, PushResult)
            skipped = set(result.skipped)
            self.assertTrue(set(result.skipped_reasons).issubset(skipped))
            self.assertTrue(set(result.skipped_details).issubset(skipped))


if __name__ == "__main__":
    unittest.main(verbosity=2)
