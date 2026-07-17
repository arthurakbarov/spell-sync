#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Line coverage for transaction safety modules."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import invalid_config_exit, run_from_scope
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.journal_schema import (
    JournalParseError,
    _validate_target_path,
    parse_bool_field,
    parse_hash_field,
    parse_journal_target,
    parse_non_empty_str,
    parse_positive_int,
    parse_transaction_id,
    parse_wordlist_state,
    validate_journal_provenance,
)
from spell_sync.push_abort import PushAbort, handle_failed_push_rollback, rollback_result_failed
from spell_sync.push_journal import JournalTarget, PushJournalSession, journal_path_for_wordlist
from spell_sync.push_prepared import (
    execute_prepared_push,
    write_rendered,
)
from spell_sync.push_render import (
    RenderedWrite,
    render_chrome_words,
    render_dictionary,
    render_hunspell_words,
    render_jetbrains_words,
    render_json_words,
    render_text_words,
    render_wordlist,
)
from spell_sync.push_transaction import PushTransaction, RollbackResult, txn_snapshot_root
from spell_sync.recover_cmd import _cmd_recover_locked
from spell_sync.sync_run import PushResult, SyncRun
from spell_sync.validated_runtime import build_validated_runtime
from tests.journal_test_utils import write_test_journal


class TestPushRenderCoverage(unittest.TestCase):
    def test_text_json_chrome_wordlist(self):
        words = frozenset({"alpha", "beta"})
        self.assertEqual(len(render_wordlist(words).sha256), 64)
        self.assertTrue(render_text_words(words, encoding="utf-8", bom=True).payload)
        self.assertIn(b"added_words", render_json_words(words).payload)
        self.assertIn(b"checksum_v1", render_chrome_words(words).payload)

    def test_hunspell_with_affix_map(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "en.dic")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("2\nalpha/AB\nbeta\n")
            with patch.dict(
                "spell_sync.push_render._HUNSPELL_AFFIX_BY_PATH",
                {path: {"alpha": "AB"}},
                clear=False,
            ):
                rendered = render_hunspell_words(frozenset({"alpha", "beta"}), path=path)
            self.assertIn(b"alpha/AB", rendered.payload)

    def test_hunspell_reads_when_no_affix_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "en.dic")
            write_text_words(path, ["solo"], "utf-8", False, quiet=True)
            rendered = render_hunspell_words(frozenset({"solo"}), path=path)
            self.assertIn(b"solo", rendered.payload)

    def test_jetbrains_existing_xml(self):
        xml = (
            '<?xml version="1.0"?>'
            '<component name="CustomDict"><words><w>old</w></words></component>'
        )
        rendered = render_jetbrains_words(frozenset({"new"}), existing_xml=xml)
        self.assertIn(b"CustomDict", rendered.payload)

    def test_jetbrains_read_from_disk_and_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.xml"
            path.write_text(
                '<?xml version="1.0"?><component name="X"><words></words></component>',
                encoding="utf-8",
            )
            dictionary = Dictionary("jb", str(path), DictionaryFormat.JETBRAINS)
            self.assertTrue(render_dictionary(dictionary, frozenset({"a"})).payload)
            with patch.object(Path, "read_text", side_effect=OSError("nope")):
                self.assertTrue(render_dictionary(dictionary, frozenset({"a"})).payload)

    def test_render_dictionary_formats(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt, name in (
                (DictionaryFormat.JSON, "prefs.json"),
                (DictionaryFormat.CHROME, "chrome.txt"),
                (DictionaryFormat.HUNSPELL, "en.dic"),
                (DictionaryFormat.TEXT, "words.txt"),
            ):
                path = os.path.join(d, name)
                if fmt is DictionaryFormat.HUNSPELL:
                    write_text_words(path, ["a"], "utf-8", False, quiet=True)
                elif fmt is DictionaryFormat.JSON:
                    Path(path).write_text("{}", encoding="utf-8")
                else:
                    Path(path).write_text("a\n", encoding="utf-8")
                dictionary = Dictionary(fmt.name.lower(), path, fmt)
                self.assertIsInstance(render_dictionary(dictionary, frozenset({"z"})).sha256, str)

    def test_write_rendered_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.txt"
            bad = RenderedWrite(b"wrong\n", "0" * 64)
            self.assertFalse(write_rendered(path, bad))


class TestJournalSchemaCoverage(unittest.TestCase):
    def test_bool_and_hash_parsers(self):
        self.assertTrue(parse_bool_field(True, field="x"))
        with self.assertRaises(JournalParseError):
            parse_bool_field("false", field="x")
        self.assertIsNone(parse_hash_field(None, field="h"))
        with self.assertRaises(JournalParseError):
            parse_hash_field(None, field="h", required=True)
        with self.assertRaises(JournalParseError):
            parse_hash_field(1, field="h")
        with self.assertRaises(JournalParseError):
            parse_hash_field("short", field="h")

    def test_int_and_str_parsers(self):
        self.assertEqual(parse_positive_int(2, field="p"), 2)
        with self.assertRaises(JournalParseError):
            parse_positive_int(0, field="p")
        with self.assertRaises(JournalParseError):
            parse_positive_int(True, field="p")
        with self.assertRaises(JournalParseError):
            parse_non_empty_str("  ", field="s")
        with self.assertRaises(JournalParseError):
            parse_transaction_id("not-a-uuid")

    def test_target_and_wordlist_schema(self):
        base = {
            "name": "d",
            "path": "/tmp/d.txt",
            "hash_before": "a" * 64,
            "hash_after": "b" * 64,
            "backup_path": None,
        }
        parsed = parse_journal_target(
            {**base, "write_started": True, "write_completed": True},
        )
        self.assertTrue(parsed["write_completed"])
        with self.assertRaises(JournalParseError):
            parse_journal_target(
                {**base, "write_completed": True, "write_started": False},
            )
        with self.assertRaises(JournalParseError):
            parse_journal_target(
                {**base, "write_completed": True, "hash_after": None},
            )
        with self.assertRaises(JournalParseError):
            parse_journal_target({**base, "backup_path": 1})
        with self.assertRaises(JournalParseError):
            parse_journal_target({**base, "path": "../etc/passwd"})

        wl = parse_wordlist_state(
            {
                "wordlist_existed_before": True,
                "wordlist_hash_before": "c" * 64,
                "wordlist_hash_after": "d" * 64,
                "wordlist_write_started": True,
                "wordlist_write_completed": True,
            },
        )
        self.assertTrue(wl["write_completed"])

    def test_validate_journal_provenance_branches(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "w.snap"
            backup.write_text("a\n", encoding="utf-8")
            target = {
                "name": "d",
                "path": str(snap / "d.txt"),
                "backup_path": str(backup),
            }
            validate_journal_provenance(
                wordlist=str(wordlist),
                transaction_id=tid,
                snapshot_dir=str(snap),
                targets=[target],
                wordlist_backup_path=str(backup),
                expected_wordlist=wordlist,
            )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[target, target],
                    wordlist_backup_path=str(backup),
                )
            validate_journal_provenance(
                wordlist=str(wordlist),
                transaction_id=tid,
                snapshot_dir=None,
                targets=[],
                wordlist_backup_path=None,
                require_snapshots=False,
            )


class TestPushAbortCoverage(unittest.TestCase):
    def test_rollback_paths(self):
        tx = MagicMock()
        tx.rollback.return_value = RollbackResult((), ("a",), ())
        session = MagicMock()
        session.mark_rollback_incomplete.side_effect = OSError("nope")
        abort = handle_failed_push_rollback(
            tx,
            session,
            reason="dictionary_write_failed",
            message="failed",
        )
        self.assertEqual(abort.reason, "rollback_incomplete")

        tx.rollback.return_value = RollbackResult(("a",), (), ())
        session.discard.side_effect = OSError("nope")
        abort2 = handle_failed_push_rollback(tx, session, reason="x", message="msg")
        self.assertEqual(abort2.exit_code, ExitCode.PUSH_ABORT)
        self.assertTrue(rollback_result_failed(RollbackResult((), ("x",), ())))


class TestPushPreparedCoverage(unittest.TestCase):
    def test_wordlist_write_and_journal_faults(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("old\n", encoding="utf-8")
            dict_path.write_text("old\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with patch(
                "spell_sync.push_prepared.write_rendered",
                side_effect=lambda path, rendered: path.name != "dict.txt",
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.exit_code, ExitCode.PUSH_ABORT)

    def test_fingerprint_during_write_and_complete_fault(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with (
                patch(
                    "spell_sync.push_prepared.write_rendered",
                    return_value=True,
                ),
                patch.object(PushJournalSession, "complete", side_effect=OSError("nope")),
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "journal_update_failed")


class TestCommandHelpersCoverage(unittest.TestCase):
    def test_invalid_config_exit_and_run_from_scope(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            (wordlist.parent / "spell-sync.toml").write_text("[bad\n", encoding="utf-8")
            code = invalid_config_exit(CliOptions(wordlist=str(wordlist)), "push")
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        self.assertEqual(run_from_scope(5), 5)
        validated = build_validated_runtime(wordlist)
        self.assertIsInstance(run_from_scope(validated), SyncRun)


class TestRecoverCmdCoverage(unittest.TestCase):
    def test_recover_validated_absent_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            validated = build_validated_runtime(wordlist)
            code = _cmd_recover_locked(
                CliOptions(wordlist=str(wordlist), json_output=True),
                validated=validated,
            )
            self.assertEqual(code, int(ExitCode.OK))


class TestPushJournalSchemaBranchCoverage(unittest.TestCase):
    def test_load_rejects_non_int_schema(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = journal_path_for_wordlist(wordlist)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "2",
                        "transaction_id": str(uuid.uuid4()),
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            from spell_sync.push_journal import JournalLoadStatus, load_journal_result

            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.UNSUPPORTED_SCHEMA,
            )

    def test_secure_file_mode_oserror(self):
        from spell_sync.push_journal import _secure_file_mode

        with patch("spell_sync.push_journal.os.chmod", side_effect=OSError("nope")):
            _secure_file_mode(Path("/tmp/x"), 0o600)


class TestPushTransactionChmodCoverage(unittest.TestCase):
    def test_backup_chmod_oserror_still_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path.write_text("a\n", encoding="utf-8")
            with patch("spell_sync.push_transaction.os.chmod", side_effect=OSError("nope")):
                tx = PushTransaction.begin(
                    wordlist,
                    [Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
                )
            tx.close()


class TestSyncRunCoverage(unittest.TestCase):
    def test_max_push_removals_from_prepared(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            run = SyncRun(wordlist=str(wordlist), dictionaries=[])
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            self.assertEqual(run.max_push_removals_from_prepared(prepared), 0)


class TestPushPreparedWordlistPath(unittest.TestCase):
    def test_wordlist_write_journal_io_errors(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            dict_path.write_text("stale\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=RenderedWrite(b"new\n", "a" * 64),
            )
            with patch.object(
                PushJournalSession,
                "mark_wordlist_write_started",
                side_effect=OSError("nope"),
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "journal_update_failed")

    def test_per_dictionary_journal_io_and_fingerprint_mid_write(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a", "b"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a", "b"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with patch.object(
                PushJournalSession,
                "mark_write_started",
                side_effect=OSError("nope"),
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)


class TestPushJournalLoadCoverage(unittest.TestCase):
    def _write_raw(self, wordlist: Path, payload: dict) -> None:
        journal_path_for_wordlist(wordlist).write_text(json.dumps(payload), encoding="utf-8")

    def test_parse_rejects_bad_schema_command_and_targets(self):
        from spell_sync.push_journal import JournalLoadStatus, load_journal_result

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            base = {
                "transaction_id": tid,
                "command": "push",
                "pid": 1,
                "started": "t",
                "state": "writing",
                "wordlist": str(wordlist),
                "targets": [],
            }
            self._write_raw(wordlist, {**base, "schema_version": True})
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.UNSUPPORTED_SCHEMA,
            )
            self._write_raw(wordlist, {**base, "schema_version": 2, "command": "nope"})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(wordlist, {**base, "schema_version": 2, "targets": "bad"})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(wordlist, {**base, "schema_version": 2, "targets": ["bad"]})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(
                wordlist,
                {**base, "schema_version": 2, "snapshot_dir": 1},
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)

    def test_snapshot_hash_mismatch_corrupt(self):
        from spell_sync.push_journal import JournalLoadStatus, load_journal_result

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "dict.snap"
            backup.write_text("wrong\n", encoding="utf-8")
            self._write_raw(
                wordlist,
                {
                    "schema_version": 2,
                    "transaction_id": tid,
                    "command": "push",
                    "pid": 1,
                    "started": "t",
                    "state": "writing",
                    "wordlist": str(wordlist),
                    "snapshot_dir": str(snap),
                    "wordlist_hash_before": "a" * 64,
                    "wordlist_backup_path": str(backup),
                    "wordlist_existed_before": True,
                    "targets": [
                        {
                            "name": "d",
                            "path": str(dict_path),
                            "hash_before": "b" * 64,
                            "hash_after": None,
                            "backup_path": str(backup),
                            "existed_before": True,
                            "write_started": True,
                            "write_completed": False,
                        }
                    ],
                },
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)


class TestRecoverJournalEdgeCases(unittest.TestCase):
    def test_failed_snapshot_hash_and_missing_destination(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_WRITING,
            PushJournal,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            target = Path(d) / "missing.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            bak.write_text("old\n", encoding="utf-8")
            wrong_hash = "0" * 64
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=wrong_hash,
                wordlist_hash_after="c" * 64,
                wordlist_backup_path=str(bak),
                wordlist_existed_before=True,
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=wrong_hash,
                        hash_after="d" * 64,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.failed)
            self.assertIn("wordlist", result.failed)


class TestJournalSchemaProvenanceErrors(unittest.TestCase):
    def test_more_validation_branches(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist.parent / ".." / "wordlist.txt"),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[],
                    wordlist_backup_path=None,
                )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(wordlist.parent / "other"),
                    targets=[],
                    wordlist_backup_path=None,
                )
            with self.assertRaises(JournalParseError):
                parse_wordlist_state({"wordlist_backup_path": 1})
            with self.assertRaises(JournalParseError):
                parse_wordlist_state(
                    {
                        "wordlist_write_completed": True,
                        "wordlist_write_started": False,
                    },
                )
            with self.assertRaises(JournalParseError):
                parse_journal_target(
                    {
                        "name": "d",
                        "path": "/tmp/d",
                        "hash_before": None,
                        "write_started": True,
                        "write_completed": False,
                    },
                )


class TestRecoverCmdValidatedFallback(unittest.TestCase):
    def test_load_when_validated_has_no_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            validated = build_validated_runtime(wordlist)
            object.__setattr__(validated, "journal_result", None)
            code = _cmd_recover_locked(
                CliOptions(wordlist=str(wordlist), json_output=True),
                validated=validated,
            )
            self.assertEqual(code, int(ExitCode.OK))


class TestPushPreparedRemainingBranches(unittest.TestCase):
    def test_write_rendered_oserror_and_early_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            write_text_words(str(dict_path), ["changed"], "utf-8", False, quiet=True)
            result = execute_prepared_push(
                prepared,
                dry_run=False,
                running_app_skip_reasons_fn=lambda _names: {},
            )
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            with patch("spell_sync.push_prepared.atomic_write", side_effect=OSError("nope")):
                prepared2 = run.prepare_push_operation()
                assert not isinstance(prepared2, ExitCode)
                result2 = execute_prepared_push(
                    prepared2,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result2, PushAbort)

    def test_wordlist_write_success_path(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            rendered = render_wordlist(prepared.words)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            result = execute_prepared_push(
                prepared,
                dry_run=False,
                running_app_skip_reasons_fn=lambda _names: {},
            )
            self.assertIsInstance(result, PushResult)

    def test_wordlist_write_render_fail_and_journal_complete_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            rendered = render_wordlist(prepared.words)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            with patch(
                "spell_sync.push_prepared.write_rendered",
                side_effect=lambda path, payload: path.name != "wordlist.txt",
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            prepared2 = replace(
                run.prepare_push_operation(),
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            assert not isinstance(prepared2, ExitCode)
            with (
                patch("spell_sync.push_prepared.write_rendered", return_value=True),
                patch.object(
                    PushJournalSession,
                    "mark_wordlist_write_completed",
                    side_effect=OSError("nope"),
                ),
            ):
                result2 = execute_prepared_push(
                    prepared2,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result2, PushAbort)

    def test_mid_write_fingerprint_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            from spell_sync.push_plan import fingerprint_conflict as real_fp

            calls = {"n": 0}

            def second_pass_conflict(dictionary, read_result):
                calls["n"] += 1
                if calls["n"] >= 2:
                    return True
                return real_fp(dictionary, read_result)

            with patch(
                "spell_sync.push_prepared.fingerprint_conflict",
                side_effect=second_pass_conflict,
            ):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "fingerprint_conflict")

    def test_writable_dictionary_missing_from_prepared_targets(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            dictionary = Dictionary("d", str(dict_path), DictionaryFormat.TEXT)
            run = SyncRun(wordlist=str(wordlist), dictionaries=[dictionary])
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            prepared = replace(prepared, targets=())
            with patch("spell_sync.push_prepared.write_rendered", return_value=True):
                result = execute_prepared_push(
                    prepared,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushResult)
            self.assertEqual(result.written, ())


class TestPushJournalRemainingBranches(unittest.TestCase):
    def test_parse_unsupported_schema_in_dict(self):
        from spell_sync.push_journal import JournalParseError, _parse_journal_dict

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            with self.assertRaises(JournalParseError):
                _parse_journal_dict(
                    {
                        "schema_version": 3,
                        "transaction_id": str(uuid.uuid4()),
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "targets": [],
                    },
                    expected_wordlist=None,
                )

    def test_wordlist_snapshot_mismatch(self):
        from spell_sync.push_journal import JournalLoadStatus, load_journal_result

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "wl.snap"
            backup.write_text("wrong\n", encoding="utf-8")
            journal_path_for_wordlist(wordlist).write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": tid,
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "snapshot_dir": str(snap),
                        "wordlist_hash_before": "0" * 64,
                        "wordlist_backup_path": str(backup),
                        "wordlist_existed_before": True,
                        "wordlist_write_started": True,
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)

    def test_recover_missing_destination_restore(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_WRITING,
            PushJournal,
            file_content_hash,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "gone.txt"
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            hb = file_content_hash(bak)
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(Path(d) / "wl.txt"),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=hb,
                        hash_after=None,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.restored)
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_recover_existing_missing_file_with_hash_after(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_WRITING,
            PushJournal,
            file_content_hash,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "gone.txt"
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            hb = file_content_hash(bak)
            ha = "f" * 64
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(Path(d) / "wl.txt"),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=hb,
                        hash_after=ha,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.restored)

    def test_discard_completed_with_snapshot_dir(self):
        from spell_sync.push_journal import discard_completed_journal

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            journal = write_test_journal(wordlist, state="completed")
            snap = Path(journal.snapshot_dir or "")
            discard_completed_journal(wordlist)
            self.assertFalse(journal_path_for_wordlist(wordlist).exists())
            if journal.snapshot_dir:
                self.assertFalse(snap.exists())


class TestPushTransactionSnapChmod(unittest.TestCase):
    def test_snap_file_chmod_oserror(self):
        from spell_sync.push_transaction import _recovery_snapshot, txn_snapshot_root

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path.write_text("a\n", encoding="utf-8")
            snap_dir = txn_snapshot_root(wordlist, str(uuid.uuid4()))
            real_chmod = os.chmod
            file_chmods = [0]

            def wrapped(path, mode, *args, **kwargs):
                if Path(path).is_file():
                    file_chmods[0] += 1
                    if file_chmods[0] > 1:
                        raise OSError("nope")
                return real_chmod(path, mode, *args, **kwargs)

            with patch("spell_sync.push_transaction.create_bak_backup"):
                with patch("spell_sync.push_transaction.os.chmod", side_effect=wrapped):
                    backup = _recovery_snapshot(dict_path, snap_dir, label="d")
            self.assertIsNotNone(backup.backup)


class TestJournalSchemaRemainingBranches(unittest.TestCase):
    def test_provenance_edge_cases(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "w.snap"
            backup.write_text("a\n", encoding="utf-8")
            target_path = str(snap / "d.txt")
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[{"name": "a", "path": target_path, "backup_path": str(backup)}],
                    wordlist_backup_path=str(backup),
                    expected_wordlist=Path(d) / "other.txt",
                )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[
                        {"name": "a", "path": target_path, "backup_path": str(backup)},
                        {"name": "b", "path": target_path, "backup_path": None},
                    ],
                    wordlist_backup_path=str(backup),
                )
            with self.assertRaises(JournalParseError):
                _validate_target_path("   ")
            with self.assertRaises(JournalParseError):
                parse_journal_target(
                    {
                        "name": "d",
                        "path": "/tmp/d",
                        "write_completed": True,
                        "write_started": True,
                        "hash_before": "a" * 64,
                    },
                )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap / ".." / wordlist.parent.name / ".spell-sync.txn" / tid),
                    targets=[],
                    wordlist_backup_path=None,
                )
            with self.assertRaises(JournalParseError):
                parse_journal_target(
                    {
                        "name": "d",
                        "path": "/tmp/d",
                        "write_completed": True,
                        "write_started": False,
                    },
                )
            outside = Path(d) / "outside.snap"
            outside.write_text("a\n", encoding="utf-8")
            validate_journal_provenance(
                wordlist=str(wordlist),
                transaction_id=tid,
                snapshot_dir=str(snap),
                targets=[],
                wordlist_backup_path=str(outside),
                require_snapshots=False,
            )
            nested = snap / "nested" / "unsafe.snap"
            nested.parent.mkdir()
            nested.write_text("a\n", encoding="utf-8")
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[
                        {
                            "name": "a",
                            "path": target_path,
                            "backup_path": str(Path("..") / "escape.snap"),
                        }
                    ],
                    wordlist_backup_path=str(backup),
                )
            tid_file = str(uuid.uuid4())
            snap_file = txn_snapshot_root(wordlist, tid_file)
            snap_file.mkdir(parents=True, exist_ok=True)
            os.rmdir(snap_file)
            snap_file.write_text("not-a-directory\n", encoding="utf-8")
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid_file,
                    snapshot_dir=str(snap_file),
                    targets=[],
                    wordlist_backup_path=None,
                )
            nested = snap / "nested"
            nested.mkdir(exist_ok=True)
            unsafe_backup = nested / ".." / backup.name
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[
                        {
                            "name": "a",
                            "path": target_path,
                            "backup_path": str(unsafe_backup),
                        }
                    ],
                    wordlist_backup_path=str(backup),
                )
            validate_journal_provenance(
                wordlist=str(wordlist),
                transaction_id=tid,
                snapshot_dir=str(snap),
                targets=[{"name": "a", "path": target_path, "backup_path": None}],
                wordlist_backup_path=str(backup),
            )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=None,
                    targets=[],
                    wordlist_backup_path=None,
                )
            missing_snap = snap / "missing.snap"
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[
                        {
                            "name": "a",
                            "path": target_path,
                            "backup_path": str(missing_snap),
                        }
                    ],
                    wordlist_backup_path=str(backup),
                )
            with self.assertRaises(JournalParseError):
                parse_wordlist_state(
                    {
                        "wordlist_write_completed": True,
                        "wordlist_write_started": True,
                        "wordlist_hash_after": None,
                    },
                )
            with self.assertRaises(JournalParseError):
                parse_wordlist_state(
                    {
                        "wordlist_existed_before": True,
                        "wordlist_write_started": True,
                        "wordlist_hash_before": None,
                    },
                )
            missing_dir = wordlist.parent / ".spell-sync.txn" / str(uuid.uuid4())
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(missing_dir),
                    targets=[],
                    wordlist_backup_path=None,
                )
            with self.assertRaises(JournalParseError):
                parse_journal_target(
                    {
                        "name": "d",
                        "path": "   ",
                    },
                )
            outside = Path(d) / "outside.snap"
            outside.write_text("a\n", encoding="utf-8")
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap),
                    targets=[
                        {
                            "name": "a",
                            "path": target_path,
                            "backup_path": str(outside),
                        }
                    ],
                    wordlist_backup_path=str(backup),
                )
            if hasattr(os, "symlink"):
                link = snap / "link.snap"
                link.symlink_to(backup)
                with self.assertRaises(JournalParseError):
                    validate_journal_provenance(
                        wordlist=str(wordlist),
                        transaction_id=tid,
                        snapshot_dir=str(snap),
                        targets=[
                            {
                                "name": "a",
                                "path": target_path,
                                "backup_path": str(link),
                            }
                        ],
                        wordlist_backup_path=str(backup),
                    )
            with self.assertRaises(JournalParseError):
                validate_journal_provenance(
                    wordlist=str(wordlist),
                    transaction_id=tid,
                    snapshot_dir=str(snap / ".." / snap.name),
                    targets=[],
                    wordlist_backup_path=None,
                )


if __name__ == "__main__":
    unittest.main()
