#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for transaction safety and recovery."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.push_transaction as push_tx_mod
import spell_sync.recover_cmd as recover_mod
from spell_sync.cli_options import CliOptions
from spell_sync.config import CHROME_CHECKSUM_PREFIX
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.read_outcome import ReadStatus, dictionary_read_result
from spell_sync.sync_run import SyncRun


def _run_cli(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    import site

    repo_root = str(Path(__file__).resolve().parents[1])
    merged = {**env}
    existing = merged.get("PYTHONPATH", "")
    parts = [repo_root, site.getusersitepackages()]
    if existing:
        parts.append(existing)
    merged["PYTHONPATH"] = os.pathsep.join(parts)
    return subprocess.run(
        [sys.executable, "-m", "spell_sync", *args],
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
    )


def _chrome_body(words: list[str]) -> str:
    return "".join(word + "\n" for word in sorted(words))


def _write_chrome(path: Path, words: list[str]) -> None:
    body = _chrome_body(words)
    checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
    path.write_text(body + CHROME_CHECKSUM_PREFIX + checksum, encoding="utf-8")


class TestConfigSafetyGate(unittest.TestCase):
    def test_corrupt_toml_blocks_push_subprocess(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path = root / "dict.txt"
            dict_path.write_text("beta\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries\nchrome = true\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["HOME"] = d
            foreign = root / "elsewhere"
            foreign.mkdir()
            proc = _run_cli(
                ["push", "-C", str(wordlist), "--yes", "--json"],
                cwd=foreign,
                env=env,
            )
            self.assertEqual(proc.returncode, int(ExitCode.PUSH_ABORT))
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["reason"], "invalid_config")
            self.assertEqual(payload["config_status"], "syntax_error")
            self.assertEqual(read_text_words(dict_path, quiet=True), {"beta"})

    def test_unknown_key_blocks_push_subprocess(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path = root / "dict.txt"
            dict_path.write_text("beta\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\ncrome = false\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["HOME"] = d
            foreign = root / "elsewhere"
            foreign.mkdir()
            proc = _run_cli(
                ["push", "-C", str(wordlist), "--yes", "--json"],
                cwd=foreign,
                env=env,
            )
            self.assertEqual(proc.returncode, int(ExitCode.PUSH_ABORT))
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["reason"], "invalid_config")
            self.assertEqual(payload["config_status"], "unknown_key")
            self.assertEqual(read_text_words(dict_path, quiet=True), {"beta"})


class TestAdjacentConfigResolution(unittest.TestCase):
    def test_cwd_irrelevant_when_adjacent_config_disables_targets(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "project"
            root.mkdir()
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\n"
                "editors = false\n"
                "chrome = false\n"
                "edge = false\n"
                "brave = false\n"
                "vivaldi = false\n"
                "firefox = false\n"
                "neovim = false\n"
                "jetbrains = false\n"
                "hunspell = false\n"
                "obsidian = false\n"
                "libreoffice = false\n",
                encoding="utf-8",
            )
            editor_path = root / "spell-sync-words.txt"
            env = os.environ.copy()
            env["HOME"] = d
            foreign = Path(d) / "foreign-cwd"
            foreign.mkdir()
            proc = _run_cli(
                ["push", "-C", str(wordlist), "--yes"],
                cwd=foreign,
                env=env,
            )
            self.assertFalse(editor_path.exists())
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "alpha\n")
            self.assertIn(proc.returncode, (int(ExitCode.OK), int(ExitCode.PARTIAL_PUSH)))


class TestChromeParser(unittest.TestCase):
    def test_missing_checksum_is_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chrome.txt"
            path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("chrome", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_valid_checksum_is_ok(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chrome.txt"
            _write_chrome(path, ["alpha"])
            dictionary = Dictionary("chrome", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.OK)
            self.assertEqual(dictionary.read(quiet=True), {"alpha"})


class TestFingerprintConflictPreservesExternalEdits(unittest.TestCase):
    def test_external_change_survives_pre_write_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["old"], "utf-8", False, quiet=True)
            dictionary = Dictionary("a", dict_path, DictionaryFormat.TEXT)
            run = SyncRun(wordlist=wordlist, dictionaries=[dictionary])

            original_begin = push_tx_mod.PushTransaction.begin

            def begin_and_mutate(wordlist_path, dictionaries, *, dry_run=False):
                tx = original_begin(wordlist_path, dictionaries, dry_run=dry_run)
                if not dry_run:
                    write_text_words(
                        dict_path,
                        ["external-change"],
                        "utf-8",
                        False,
                        quiet=True,
                    )
                return tx

            with patch.object(
                push_tx_mod.PushTransaction,
                "begin",
                side_effect=begin_and_mutate,
            ):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(
                read_text_words(dict_path, quiet=True),
                {"external-change"},
            )


class TestCorruptJournalRecover(unittest.TestCase):
    def test_corrupt_journal_not_reported_as_absent(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = wordlist.parent / ".spell-sync.journal.json"
            journal.write_text("{not json", encoding="utf-8")
            code = recover_mod.cmd_recover(
                CliOptions(wordlist=str(wordlist), json_output=True),
            )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertTrue(journal.is_file())


class TestStaleLockMetadata(unittest.TestCase):
    def test_live_foreign_pid_does_not_block_when_flock_free(self):
        from spell_sync.operation_lock import acquire_operation_lock

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = wordlist.parent / ".spell-sync.lock"
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": os.getppid(),
                        "started": "2020-01-01T00:00:00+00:00",
                        "command": "push",
                        "wordlist": str(wordlist),
                    }
                ),
                encoding="utf-8",
            )
            with acquire_operation_lock(wordlist, "push"):
                pass


class TestRecoveryCreatedFileSafety(unittest.TestCase):
    def test_recovery_does_not_delete_unknown_new_file(self):
        from spell_sync.push_journal import (
            JournalTarget,
            PushJournal,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            created = Path(d) / "created.txt"
            created.write_text("other-process\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(__import__("uuid").uuid4()),
                command="push",
                pid=1,
                started="2026-01-01T00:00:00+00:00",
                state="writing",
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="created",
                        path=str(created),
                        hash_before=None,
                        hash_after=None,
                        backup_path=None,
                        existed_before=False,
                        write_started=False,
                        write_completed=False,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("created", result.skipped)
            self.assertTrue(created.is_file())


class TestCoverage101(unittest.TestCase):
    def test_invalid_config_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text("[bad\n", encoding="utf-8")
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = __import__("spell_sync.commands", fromlist=["cmd_pull"]).cmd_pull(
                    CliOptions(wordlist=str(wordlist))
                )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertIn("invalid spell-sync.toml", buf.getvalue())

    def test_recover_corrupt_journal_and_discard(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (wordlist.parent / ".spell-sync.journal.json").write_text("{bad", encoding="utf-8")
            code = recover_mod.cmd_recover(
                CliOptions(wordlist=str(wordlist), json_output=True),
            )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            code = recover_mod.cmd_recover(
                CliOptions(
                    wordlist=str(wordlist),
                    discard_corrupt_journal=True,
                ),
            )
            self.assertEqual(code, int(ExitCode.OK))
            self.assertFalse((wordlist.parent / ".spell-sync.journal.json").exists())

    def test_recover_completed_journal_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            from tests.journal_test_utils import write_test_journal

            write_test_journal(wordlist, state="completed")
            code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_chrome_parser_edge_cases(self):
        from spell_sync.read_outcome import dictionary_read_result

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.txt"
            body = "alpha\n"
            checksum = hashlib.md5(body.encode()).hexdigest()
            path.write_bytes(b"\xff\xfe")
            dictionary = Dictionary("c", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

            path.write_text(
                "alpha\nchecksum_v1 = " + checksum + "\nchecksum_v1 = " + checksum,
                encoding="utf-8",
            )
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

            path.write_text(body + "checksum_v1 = deadbeef", encoding="utf-8")
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

            path.write_text(body + "checksum_v1 = " + ("0" * 32) + "\ntrailing", encoding="utf-8")
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

            path.write_text(body + "checksum_v1 = " + ("0" * 32), encoding="utf-8")
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

            fake_path = str(path)

            class FakeDictionary:
                path = fake_path
                format = object()

            result = dictionary_read_result(FakeDictionary())  # type: ignore[arg-type]
            self.assertEqual(result.status, ReadStatus.UNSUPPORTED)

    def test_rollback_incomplete_paths(self):
        from spell_sync.push_journal import PushJournalSession
        from spell_sync.push_transaction import (
            PushTransaction,
            TargetWriteState,
            _FileBackup,
            rollback_backups,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("old\n", encoding="utf-8")
            dictionary = Dictionary("d", str(dict_path), DictionaryFormat.TEXT)
            tx = PushTransaction.begin(wordlist, [dictionary], dry_run=False)
            session = PushJournalSession.begin(
                wordlist,
                command="push",
                tx=tx,
                dictionaries=[dictionary],
            )
            session.mark_rollback_incomplete()
            tx.close()

            snap = Path(d) / "snap"
            snap.write_text("old\n", encoding="utf-8")
            failed_bak = _FileBackup(dict_path, snap, True, "d")
            failed_bak.write_state = TargetWriteState.WRITE_STARTED
            missing_snap = _FileBackup(dict_path, None, True, "d2")
            missing_snap.write_state = TargetWriteState.WRITE_STARTED
            new_gone = _FileBackup(Path(d) / "gone.txt", None, False, "gone")
            new_gone.write_state = TargetWriteState.WRITE_STARTED
            rollback_backups([new_gone])

            ok_path = Path(d) / "ok.txt"
            ok_bak = _FileBackup(ok_path, snap, True, "ok")
            ok_bak.write_state = TargetWriteState.WRITE_STARTED
            real_copy2 = __import__("shutil").copy2

            def selective_copy(src, dst, *, _real=real_copy2):
                if Path(dst).resolve() == dict_path.resolve():
                    raise OSError("nope")
                return _real(src, dst)

            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                with patch(
                    "spell_sync.push_transaction.shutil.copy2",
                    side_effect=selective_copy,
                ):
                    tx2 = PushTransaction(
                        dictionary_backups=[ok_bak, failed_bak],
                        wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                        transaction_id="x",
                        snapshot_dir=None,
                        _backups_cm=_NoopExit(),
                    )
                    result = tx2.rollback()
            self.assertIn("d", result.failed)
            self.assertIn("ok", result.restored)
            self.assertIn("rollback incomplete", buf.getvalue())

            buf2 = __import__("io").StringIO()
            only_fail = _FileBackup(dict_path, snap, True, "only")
            only_fail.write_state = TargetWriteState.WRITE_STARTED
            with __import__("contextlib").redirect_stdout(buf2):
                with patch(
                    "spell_sync.push_transaction.shutil.copy2",
                    side_effect=OSError("nope"),
                ):
                    tx3 = PushTransaction(
                        dictionary_backups=[only_fail],
                        wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                        transaction_id="y",
                        snapshot_dir=None,
                        _backups_cm=_NoopExit(),
                    )
                    tx3.rollback()
            self.assertIn("rollback failed for", buf2.getvalue())
            partial = rollback_backups([missing_snap])
            self.assertIn("d2", partial.failed)

    def test_runtime_context_explicit_config(self):
        from spell_sync.sync_context import RuntimeContext

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ctx = RuntimeContext.build(
                wordlist=wordlist,
                config={"dictionaries": {"chrome": False}},
            )
            self.assertFalse(ctx.config["dictionaries"]["chrome"])

    def test_max_local_without_explicit_words(self):
        from spell_sync.push_setup import max_local_dictionary_count
        from spell_sync.sync_context import RuntimeContext

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_text_words(dict_path, ["beta", "gamma"], "utf-8", False, quiet=True)
            ctx = RuntimeContext.build(
                wordlist=wordlist,
                dictionaries=[Dictionary("d", dict_path, DictionaryFormat.TEXT)],
            )
            self.assertEqual(max_local_dictionary_count(ctx), 2)

    def test_max_local_returns_zero_when_plan_aborts(self):
        from spell_sync.push_setup import max_local_dictionary_count
        from spell_sync.sync_context import RuntimeContext

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            ctx = RuntimeContext.build(wordlist=wordlist, dictionaries=[])
            with patch(
                "spell_sync.push_setup.build_push_plan",
                return_value=ExitCode.PUSH_ABORT,
            ):
                self.assertEqual(max_local_dictionary_count(ctx), 0)

    def test_push_transaction_helpers(self):
        from spell_sync.push_transaction import PushTransaction

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("d", str(dict_path), DictionaryFormat.TEXT)
            tx = PushTransaction.begin(wordlist, [dictionary], dry_run=False)
            missing = Dictionary("x", "/nope", DictionaryFormat.TEXT)
            self.assertIsNone(tx.backup_for_dictionary(missing))
            tx.mark_write_started(dictionary)
            tx.mark_write_completed(dictionary)
            tx.mark_wordlist_write_started()
            tx.mark_wordlist_write_completed()
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                tx.rollback()
            self.assertIn("rolled back", buf.getvalue())
            tx.close()

    def test_wordlist_write_failure_marks_rollback_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch("spell_sync.push_setup.wordlist_needs_rewrite", return_value=True),
                patch("spell_sync.push_prepared.write_rendered", return_value=False),
                patch.object(
                    push_tx_mod.PushTransaction,
                    "rollback",
                    return_value=push_tx_mod.RollbackResult((), ("wordlist",), ()),
                ),
            ):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_recover_corrupt_journal_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (wordlist.parent / ".spell-sync.journal.json").write_text("{bad", encoding="utf-8")
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertIn("corrupt", buf.getvalue().lower())

    def test_mutating_scope_yields_config_exit(self):
        from spell_sync.command_helpers import mutating_command_scope

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (wordlist.parent / "spell-sync.toml").write_text("[bad\n", encoding="utf-8")
            with mutating_command_scope(CliOptions(wordlist=str(wordlist)), "pull") as scope:
                self.assertEqual(scope, int(ExitCode.PUSH_ABORT))

    def test_chrome_empty_body_with_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.txt"
            path.write_text("!!!\nchecksum_v1 = " + ("a" * 32), encoding="utf-8")
            dictionary = Dictionary("c", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_invalid_config_json_exit(self):
        from spell_sync.command_helpers import invalid_config_exit

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (wordlist.parent / "spell-sync.toml").write_text("[bad\n", encoding="utf-8")
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = invalid_config_exit(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                    "push",
                )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["reason"], "invalid_config")

    def test_recover_completed_journal_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            from tests.journal_test_utils import write_test_journal

            write_test_journal(wordlist, state="completed")
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                )
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(json.loads(buf.getvalue())["action"], "cleanup")

    def test_recover_discard_corrupt_journal_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (wordlist.parent / ".spell-sync.journal.json").write_text("{bad", encoding="utf-8")
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(
                        wordlist=str(wordlist),
                        json_output=True,
                        discard_corrupt_journal=True,
                    ),
                )
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(
                json.loads(buf.getvalue())["action"],
                "discarded_corrupt_journal",
            )

    def test_recover_rollback_incomplete_json_reason(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_ROLLBACK_INCOMPLETE,
        )
        from tests.journal_test_utils import write_test_journal

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_ROLLBACK_INCOMPLETE,
            )
            buf = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), yes=True, json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(payload.get("reason"), "rollback_incomplete")

    def test_chrome_whitespace_only_body(self):
        body = "\n"
        checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.txt"
            path.write_text(body + "checksum_v1 = " + checksum, encoding="utf-8")
            dictionary = Dictionary("c", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_chrome_direct_empty_and_invalid_tokens(self):
        from spell_sync.read_outcome import ReadStatus as RS
        from spell_sync.read_outcome import _chrome_read_result

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.txt"
            empty = _chrome_read_result(path, b"")
            self.assertEqual(empty.status, RS.EMPTY)
            body = "!!!\n"
            checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
            path.write_text(body + "checksum_v1 = " + checksum, encoding="utf-8")
            with patch("spell_sync.read_outcome.normalize_token", return_value=""):
                corrupt = _chrome_read_result(path, path.read_bytes())
            self.assertEqual(corrupt.status, RS.CORRUPT)

    def test_recover_new_file_missing_and_hash_conflict(self):
        from spell_sync.push_journal import (
            JOURNAL_SCHEMA_VERSION,
            JOURNAL_STATE_WRITING,
            JournalTarget,
            PushJournal,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            created = Path(d) / "new.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id=str(__import__("uuid").uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                targets=[
                    JournalTarget(
                        name="new",
                        path=str(created),
                        hash_before=None,
                        hash_after="0" * 64,
                        backup_path=None,
                        existed_before=False,
                        write_started=True,
                        write_completed=True,
                    ),
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("new", result.skipped)
            created.write_text("other\n", encoding="utf-8")
            result = recover_from_journal(journal)
            self.assertIn("new", result.conflicts)


class TestJournalStrictBooleanFields(unittest.TestCase):
    def test_string_false_booleans_are_corrupt_not_in_progress(self):
        from spell_sync.push_journal import JournalLoadStatus, load_journal_result

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": str(__import__("uuid").uuid4()),
                        "command": "push",
                        "pid": 1,
                        "started": "2026-01-01T00:00:00+00:00",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "targets": [
                            {
                                "name": "d",
                                "path": str(wordlist.parent / "d.txt"),
                                "hash_before": None,
                                "hash_after": None,
                                "backup_path": None,
                                "existed_before": "false",
                                "write_started": "false",
                                "write_completed": "false",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_journal_result(wordlist)
            self.assertEqual(loaded.status, JournalLoadStatus.CORRUPT)


class TestImmutablePushPlan(unittest.TestCase):
    def test_post_confirm_dictionary_mutation_aborts_without_silent_removals(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            words = [f"word{i:02d}" for i in range(11)]
            write_text_words(wordlist, words, "utf-8", False, quiet=True)
            write_text_words(dict_path, words, "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("d", dict_path, DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            self.assertEqual(prepared.max_removals(), 0)
            extra = words + [f"extra{i:02d}" for i in range(60)]
            write_text_words(dict_path, extra, "utf-8", False, quiet=True)
            result = run.push_from_wordlist(prepared=prepared)
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(read_text_words(dict_path, quiet=True), set(extra))


class TestCrashRecoveryMatrix(unittest.TestCase):
    """Parametric crash-point expectations for journal recovery."""

    def test_matrix(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_ROLLBACK_INCOMPLETE,
            cleanup_after_successful_recovery,
            recover_from_journal,
        )
        from tests.journal_test_utils import write_restore_scenario_journal, write_test_journal

        cases = [
            ("existing_dict_post_image", lambda wl, dp: write_restore_scenario_journal(wl, dp)),
            (
                "wordlist_before_replace",
                lambda wl, _dp: write_test_journal(
                    wl,
                    wordlist_write_started=True,
                    wordlist_write_completed=False,
                ),
            ),
            (
                "rollback_incomplete",
                lambda wl, _dp: write_test_journal(
                    wl,
                    state=JOURNAL_STATE_ROLLBACK_INCOMPLETE,
                ),
            ),
        ]
        for label, setup in cases:
            with self.subTest(crash_point=label):
                with tempfile.TemporaryDirectory() as d:
                    wordlist = Path(d) / "wordlist.txt"
                    dict_path = Path(d) / "dict.txt"
                    wordlist.write_text("old\n", encoding="utf-8")
                    dict_path.write_text("old\n", encoding="utf-8")
                    journal = setup(wordlist, dict_path)
                    if label == "existing_dict_post_image":
                        result = recover_from_journal(journal)
                        self.assertIn("d", result.restored)
                        self.assertEqual(dict_path.read_text(encoding="utf-8"), "old\n")
                        cleanup_after_successful_recovery(journal)
                        self.assertFalse(
                            push_tx_mod.txn_snapshot_root(
                                wordlist,
                                journal.transaction_id,
                            ).exists()
                        )
                    elif label == "wordlist_before_replace":
                        result = recover_from_journal(journal)
                        self.assertNotIn("wordlist", result.conflicts)
                    elif label == "rollback_incomplete":
                        self.assertEqual(journal.state, JOURNAL_STATE_ROLLBACK_INCOMPLETE)
                        result = recover_from_journal(journal)
                        self.assertFalse(result.failed)


class _NoopExit:
    def __exit__(self, exc_type, exc, tb) -> None:
        return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
