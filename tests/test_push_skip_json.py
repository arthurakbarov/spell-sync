#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push skip_reasons / skipped_details JSON and preflight classification."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import finish_push
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.skip_reasons import PushSkipReason
from spell_sync.sync_run import PushResult, SyncRun


class TestPushSkipClassification(unittest.TestCase):
    def test_blocked_dict_not_labeled_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_blocked, ["other"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                    Dictionary("blocked", path_blocked, DictionaryFormat.TEXT),
                ],
            )
            result = run.plan_push(skip_names=frozenset({"blocked"}))
            assert isinstance(result, PushResult)
            self.assertEqual(result.skipped_reasons.get("blocked"), PushSkipReason.BLOCKED_BY_USER)
            self.assertNotEqual(
                result.skipped_reasons.get("blocked"),
                PushSkipReason.UNREADABLE,
            )
            self.assertIn("blocked before push", result.skipped_details.get("blocked", ""))
            self.assertEqual(result.written, ("ok",))

    def test_unreadable_dict_labeled_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_secret = os.path.join(d, "secret.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_secret, ["x"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                    Dictionary("secret", path_secret, DictionaryFormat.TEXT),
                ],
            )

            def readable(path):
                return str(path) != path_secret

            patch_target = "spell_sync.read_outcome.is_path_readable"
            with patch(patch_target, side_effect=lambda p: readable(p)):
                result = run.plan_push()
            assert isinstance(result, PushResult)
            self.assertEqual(result.skipped_reasons.get("secret"), PushSkipReason.UNREADABLE)
            self.assertIn("no access", result.skipped_details.get("secret", ""))
            self.assertEqual(result.written, ("ok",))


class TestPushSkipJson(unittest.TestCase):
    def test_push_json_includes_skipped_details_for_backup_fail(self):
        result = PushResult(
            2,
            ("ok",),
            ("bad",),
            skipped_reasons={"bad": PushSkipReason.BACKUP_FAILED},
            skipped_details={"bad": "backup failed — push skipped"},
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = finish_push(result, CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["skipped_reasons"]["bad"], "backup_failed")
        self.assertEqual(payload["skipped_details"]["bad"], "backup failed — push skipped")
