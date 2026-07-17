#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safety invariants: lock, backup_keep=0, TOML, journal completion, recover."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.settings as settings_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.operation_lock import acquire_operation_lock
from spell_sync.push_journal import (
    JournalLoadStatus,
    PushJournalSession,
    load_journal_result,
)
from spell_sync.sync_run import SyncRun


class TestTomlConsistentSemantics(unittest.TestCase):
    def setUp(self) -> None:
        settings_mod.clear_settings_cache()

    def tearDown(self) -> None:
        settings_mod.clear_settings_cache()

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def test_enabled_yes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            self._write(path, "[dictionaries]\nchrome = yes\n")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_bytes_path_loads_as_text(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            self._write(path, "[dictionaries]\nchrome = true\n")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(issues, [])
            self.assertTrue(data["dictionaries"]["chrome"])

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            self._write(path, "[dictionaries]\nchrome = true\nchrome = false\n")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertTrue(issues)
            self.assertEqual(data, {})

    def test_trailing_garbage_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            self._write(path, "[dictionaries]\nchrome = true\n]]]nonsense\n")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertTrue(issues)
            self.assertEqual(data, {})


class TestLockSplitBrain(unittest.TestCase):
    def test_subprocess_cannot_steal_lock_with_dead_pid_metadata(self):
        """Kernel lock is truth; wrong/dead PID in metadata must not unlock."""
        if sys.platform == "win32":
            self.skipTest("Windows cannot rewrite an exclusively locked lock file")
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = wordlist.parent / ".spell-sync.lock"
            script = textwrap.dedent(
                f"""
                import sys
                from pathlib import Path
                from spell_sync.operation_lock import OperationLocked, acquire_operation_lock
                wordlist = Path({str(wordlist)!r})
                try:
                    with acquire_operation_lock(wordlist, "child"):
                        pass
                except OperationLocked:
                    sys.exit(17)
                sys.exit(0)
                """
            )
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
            with acquire_operation_lock(wordlist, "parent"):
                # Poison metadata with a PID that does not exist
                lock_path.write_text(
                    json.dumps(
                        {
                            "pid": 1_000_000_007,
                            "started": "2020-01-01T00:00:00+00:00",
                            "command": "poison",
                            "wordlist": str(wordlist),
                        }
                    ),
                    encoding="utf-8",
                )
                proc = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=d,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            self.assertEqual(
                proc.returncode,
                17,
                msg=f"stdout={proc.stdout!r} stderr={proc.stderr!r}",
            )


class TestBackupKeepZeroRollback(unittest.TestCase):
    def test_rollback_uses_transaction_snapshot_not_stale_bak(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            a = Path(d) / "a.txt"
            b = Path(d) / "b.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            a.write_text("before-a\n", encoding="utf-8")
            b.write_text("before-b\n", encoding="utf-8")
            # Stale user bak must NOT be used as transaction snapshot
            Path(str(a) + ".bak").write_text("ancient-stale\n", encoding="utf-8")

            dictionaries = [
                Dictionary("a", a, DictionaryFormat.TEXT),
                Dictionary("b", b, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=str(wordlist), dictionaries=dictionaries)

            write_count = {"n": 0}
            import spell_sync.push_prepared as push_prepared

            original_write_rendered = push_prepared.write_rendered

            def flaky_write_rendered(path, rendered):
                write_count["n"] += 1
                if write_count["n"] == 1:
                    return original_write_rendered(path, rendered)
                return False

            with (
                patch("spell_sync.config.backup_keep_count", return_value=0),
                patch.object(push_prepared, "write_rendered", flaky_write_rendered),
            ):
                result = run.push_from_wordlist()

            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(a.read_text(encoding="utf-8"), "before-a\n")
            self.assertEqual(b.read_text(encoding="utf-8"), "before-b\n")
            self.assertNotEqual(a.read_text(encoding="utf-8"), "ancient-stale\n")


class TestSamplePrefixCorruption(unittest.TestCase):
    def test_corruption_after_sample_detected_as_corrupt(self):
        from spell_sync.io import _DETECT_SAMPLE_BYTES
        from spell_sync.read_outcome import ReadStatus, dictionary_read_result

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "big.txt"
            # Valid ASCII in sample window, then invalid UTF-8 after limit
            good = ("word\n" * ((_DETECT_SAMPLE_BYTES // 5) + 10)).encode("utf-8")
            blob = good[:_DETECT_SAMPLE_BYTES] + b"\xff\xfe invalid"
            path.write_bytes(blob)
            result = dictionary_read_result(
                Dictionary("big", path, DictionaryFormat.TEXT),
            )
            self.assertEqual(result.status, ReadStatus.CORRUPT)
            self.assertIsNotNone(result.fingerprint)


class TestFingerprintConflict(unittest.TestCase):
    def test_push_aborts_when_target_changes_after_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wordlist = root / "wordlist.txt"
            target = root / "dict.txt"
            wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
            target.write_text("alpha\n", encoding="utf-8")

            dictionary = Dictionary("dict", target, DictionaryFormat.TEXT)
            run = SyncRun(wordlist=str(wordlist), dictionaries=[dictionary])
            from spell_sync.push_transaction import PushTransaction

            original_begin = PushTransaction.begin

            def begin_and_corrupt(wordlist_path, dictionaries, *, dry_run=False):
                tx = original_begin(wordlist_path, dictionaries, dry_run=dry_run)
                if not dry_run:
                    target.write_text("changed-after-plan\n", encoding="utf-8")
                return tx

            with patch.object(PushTransaction, "begin", side_effect=begin_and_corrupt):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(target.read_text(encoding="utf-8"), "changed-after-plan\n")


class TestJournalCompletion(unittest.TestCase):
    def test_complete_marks_completed_before_unlink(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "a.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            from spell_sync.push_transaction import PushTransaction

            dictionaries = [Dictionary("a", dict_path, DictionaryFormat.TEXT)]
            tx = PushTransaction.begin(wordlist, dictionaries)
            try:
                session = PushJournalSession.begin(
                    wordlist,
                    command="push",
                    tx=tx,
                    dictionaries=dictionaries,
                )
                journal_path = wordlist.parent / ".spell-sync.journal.json"

                def fail_unlink(*_args, **_kwargs):
                    raise OSError("simulated unlink failure")

                with patch.object(Path, "unlink", fail_unlink):
                    session.complete()
                loaded = load_journal_result(wordlist)
                self.assertEqual(loaded.status, JournalLoadStatus.VALID_COMPLETED)
                self.assertTrue(journal_path.is_file())
                # Recover of completed journal must not roll back successful push
                # (discard_completed_or_warn path)
            finally:
                tx.close()
            # Cleanup for next tests
            try:
                (wordlist.parent / ".spell-sync.journal.json").unlink(missing_ok=True)
            except OSError:
                pass


class TestJournalLoadTyped(unittest.TestCase):
    def test_list_root_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            path.write_text("[]\n", encoding="utf-8")
            loaded = load_journal_result(wordlist)
            self.assertEqual(loaded.status, JournalLoadStatus.CORRUPT)

    def test_path_traversal_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": "t",
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "wordlist_hash_before": None,
                        "wordlist_backup_path": None,
                        "targets": [
                            {
                                "name": "evil",
                                "path": "../etc/passwd",
                                "hash_before": None,
                                "backup_path": None,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_journal_result(wordlist)
            self.assertEqual(loaded.status, JournalLoadStatus.CORRUPT)

    def test_preparing_and_recovered_states(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            base = {
                "schema_version": 2,
                "transaction_id": "t",
                "command": "push",
                "pid": 1,
                "started": "t",
                "wordlist": str(wordlist),
                "wordlist_hash_before": None,
                "wordlist_backup_path": None,
                "targets": [],
            }
            path.write_text(json.dumps({**base, "state": "preparing"}), encoding="utf-8")
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.CORRUPT,
            )
            path.write_text(json.dumps({**base, "state": "recovered"}), encoding="utf-8")
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.CORRUPT,
            )

    def test_corrupt_journal_blocks_mutator(self):
        import spell_sync.commands as commands
        from spell_sync.cli_options import CliOptions
        from spell_sync.exit_codes import ExitCode

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            (wordlist.parent / ".spell-sync.journal.json").write_text("[]\n", encoding="utf-8")
            code = commands.cmd_pull(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))


class TestRecoverCreatedTarget(unittest.TestCase):
    def test_removes_new_file_created_by_txn(self):
        from spell_sync.push_journal import (
            JOURNAL_SCHEMA_VERSION,
            JOURNAL_STATE_WRITING,
            JournalTarget,
            PushJournal,
            file_content_hash,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            created = Path(d) / "new-dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            created.write_text("created\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id="00000000-0000-4000-8000-000000000003",
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="new",
                        path=str(created),
                        hash_before=None,
                        hash_after=file_content_hash(created),
                        backup_path=None,
                        existed_before=False,
                        write_started=True,
                        write_completed=True,
                    ),
                ],
            )
            # Provide wordlist snapshot so wordlist restore does not fail
            bak = Path(d) / "wordlist.txt.bak"
            bak.write_text("alpha\n", encoding="utf-8")
            journal.wordlist_backup_path = str(bak)
            result = recover_from_journal(journal)
            self.assertIn("new", result.restored)
            self.assertFalse(created.exists())

    def test_conflict_keeps_failure(self):
        from spell_sync.push_journal import (
            JOURNAL_SCHEMA_VERSION,
            JOURNAL_STATE_WRITING,
            PushJournal,
            file_content_hash,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("third-party-change\n", encoding="utf-8")
            bak = Path(d) / "wordlist.txt.snap"
            bak.write_text("original\n", encoding="utf-8")
            hash_before = file_content_hash(bak)
            txn_written = Path(d) / "txn-written.txt"
            txn_written.write_text("txn-applied\n", encoding="utf-8")
            hash_after = file_content_hash(txn_written)
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id="00000000-0000-4000-8000-000000000001",
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=hash_before,
                wordlist_hash_after=hash_after,
                wordlist_backup_path=str(bak),
                wordlist_existed_before=True,
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[],
            )
            result = recover_from_journal(journal)
            self.assertIn("wordlist", result.conflicts)


class TestSafetyCoverageExtras(unittest.TestCase):
    def test_journal_targets_type_errors_and_unknown_state(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            base = {
                "schema_version": 2,
                "transaction_id": "t",
                "command": "push",
                "pid": 1,
                "started": "t",
                "wordlist": str(wordlist),
                "targets": "nope",
            }
            path.write_text(json.dumps({**base, "state": "writing"}), encoding="utf-8")
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            base["targets"] = ["not-object"]
            path.write_text(json.dumps({**base, "state": "writing"}), encoding="utf-8")
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            base["targets"] = []
            path.write_text(json.dumps({**base, "state": "weird"}), encoding="utf-8")
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)

    def test_recover_dry_run_new_file_and_unlink_failure(self):
        from spell_sync.push_journal import (
            JOURNAL_SCHEMA_VERSION,
            JOURNAL_STATE_WRITING,
            JournalTarget,
            PushJournal,
            discard_completed_journal,
            file_content_hash,
            recover_from_journal,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            created = Path(d) / "new.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            created.write_text("x\n", encoding="utf-8")
            bak = Path(d) / "wl.snap"
            bak.write_text("a\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id="00000000-0000-4000-8000-000000000003",
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_backup_path=str(bak),
                wordlist_existed_before=True,
                wordlist_hash_after=None,
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[
                    JournalTarget(
                        name="new",
                        path=str(created),
                        hash_before=None,
                        hash_after=file_content_hash(created),
                        backup_path=None,
                        existed_before=False,
                        write_started=True,
                        write_completed=True,
                    ),
                ],
            )
            dry = recover_from_journal(journal, dry_run=True)
            self.assertIn("new", dry.restored)
            with patch.object(Path, "unlink", side_effect=OSError("nope")):
                failed = recover_from_journal(journal)
            self.assertIn("new", failed.failed)
            path = wordlist.parent / ".spell-sync.journal.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": "00000000-0000-4000-8000-000000000004",
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "completed",
                        "wordlist": str(wordlist),
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            discard_completed_journal(wordlist)
            self.assertFalse(path.exists())

    def test_corrupt_journal_json_and_completed_noop(self):
        import io
        from contextlib import redirect_stdout

        import spell_sync.commands as commands
        from spell_sync.cli_options import CliOptions
        from spell_sync.command_helpers import unfinished_journal_exit
        from spell_sync.exit_codes import ExitCode

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = wordlist.parent / ".spell-sync.journal.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": "00000000-0000-4000-8000-000000000002",
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "completed",
                        "wordlist": str(wordlist),
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(unfinished_journal_exit(CliOptions(wordlist=str(wordlist)), "pull"))
            path.write_text("[]\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertEqual(json.loads(buf.getvalue())["reason"], "corrupt_journal")

    def test_txn_discard_snapshots(self):
        from spell_sync.push_transaction import discard_txn_snapshots

        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / ".spell-sync.txn" / "tid"
            root.mkdir(parents=True)
            (root / "x.snap").write_text("a", encoding="utf-8")
            discard_txn_snapshots(root)
            self.assertFalse(root.exists())
            discard_txn_snapshots(None)

    def test_recover_conflicts_message(self):
        from spell_sync.exit_codes import ExitCode
        from spell_sync.push_journal import RecoverResult
        from spell_sync.recover_cmd import _emit_recover_text

        code = _emit_recover_text(
            RecoverResult((), (), (), ("wordlist",)),
            dry_run=False,
        )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_invalid_type_keeps_partial_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("orphan = true\n[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[path]):
                result = settings_mod.load_config_result(reload=True)
            self.assertEqual(result.status, settings_mod.ConfigStatus.INVALID_TYPE)
            assert result.config is not None
            self.assertTrue(result.config["dictionaries"]["chrome"])

    def test_unknown_key_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\nchrome = true\nweird = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[path]):
                result = settings_mod.load_config_result(reload=True)
            self.assertEqual(result.status, settings_mod.ConfigStatus.UNKNOWN_KEY)
        settings_mod.clear_settings_cache()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[push]\nstrict = true\n", encoding="utf-8")
            with patch.object(settings_mod.tomllib, "loads", side_effect=TypeError("nope")):
                data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)
            with patch.object(settings_mod, "config_paths", return_value=[]):
                result = settings_mod.load_config_result(reload=True)
            self.assertEqual(result.status, settings_mod.ConfigStatus.ABSENT)
            self.assertTrue(
                settings_mod.config_blocks_mutating(
                    settings_mod.ConfigLoadResult(
                        settings_mod.ConfigStatus.SYNTAX_ERROR,
                        None,
                        (),
                    )
                )
            )
            # Force remaining parse helpers when data empty via issues
            with patch.object(
                settings_mod,
                "_parse_toml_with_issues",
                return_value=({}, ["hard fail"]),
            ):
                result = settings_mod.load_config_result(reload=True)
            # config_paths still empty → ABSENT
            with patch.object(
                settings_mod,
                "config_paths",
                return_value=[Path(d) / "spell-sync.toml"],
            ):
                path.write_text("[push]\nstrict = true\nbad\n", encoding="utf-8")
                # invalid file via tomllib
                path.write_text("[push]\nstrict = true\nstrict = false\n", encoding="utf-8")
                settings_mod.clear_settings_cache()
                result = settings_mod.load_config_result(reload=True)
                self.assertEqual(result.status, settings_mod.ConfigStatus.SYNTAX_ERROR)

    def test_pid_alive_permission_error_covered(self):
        if sys.platform == "win32":
            self.skipTest("Windows uses OpenProcess, not os.kill")
        from spell_sync.operation_lock import _pid_alive

        with patch("spell_sync.operation_lock.os.kill", side_effect=PermissionError):
            self.assertTrue(_pid_alive(123))

    def test_pid_alive_current_process(self):
        from spell_sync.operation_lock import _pid_alive

        self.assertTrue(_pid_alive(os.getpid()))

    def test_discard_txn_rmdir_oserror(self):
        from spell_sync.push_transaction import discard_txn_snapshots

        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / ".spell-sync.txn" / "tid"
            root.mkdir(parents=True)
            with patch("shutil.rmtree", side_effect=OSError("nope")):
                discard_txn_snapshots(root)
            # still exists because rmtree failed
            self.assertTrue(root.exists())
            with (
                patch("shutil.rmtree"),
                patch.object(Path, "rmdir", side_effect=OSError("busy")),
            ):
                discard_txn_snapshots(root)


class TestWritabilityAndFingerprintCoverage(unittest.TestCase):
    def test_is_path_writable_success_and_failures(self):
        from spell_sync.io import is_path_writable

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "dict.txt"
            target.write_text("a\n", encoding="utf-8")
            self.assertTrue(is_path_writable(target))
            self.assertTrue(is_path_writable(root / "missing.txt"))
            self.assertFalse(is_path_writable(root / "nope" / "nested.txt"))

            with patch("tempfile.mkstemp", side_effect=OSError("deny")):
                self.assertFalse(is_path_writable(target))

            with patch("os.replace", side_effect=OSError("rename fail")):
                self.assertFalse(is_path_writable(target))

            with patch("os.access", return_value=False):
                self.assertFalse(is_path_writable(target))

            link = root / "link.txt"
            link.symlink_to(target)
            self.assertFalse(is_path_writable(link))

            with (
                patch("os.write", side_effect=OSError("write fail")),
                patch("os.close"),
            ):
                if sys.platform == "win32":
                    self.skipTest("Windows probe cleanup differs when os.close is patched")
                self.assertFalse(is_path_writable(target))

    def test_fingerprint_helpers(self):
        from spell_sync.read_outcome import (
            ReadStatus,
            _fingerprint,
            dictionary_read_result,
            fingerprint_matches,
        )

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.txt"
            path.write_text("alpha\n", encoding="utf-8")
            raw = path.read_bytes()
            fp = _fingerprint(path, raw)
            self.assertTrue(fingerprint_matches(path, fp))
            self.assertTrue(fingerprint_matches(Path(d) / "missing.txt", None))
            self.assertFalse(fingerprint_matches(path, None))
            self.assertFalse(fingerprint_matches(Path(d) / "missing.txt", fp))

            with patch.object(Path, "stat", side_effect=OSError("stat")):
                fp2 = _fingerprint(path, raw)
                self.assertEqual(fp2.size, len(raw))

            with patch.object(Path, "read_bytes", side_effect=OSError("nope")):
                self.assertFalse(fingerprint_matches(path, fp))

            jb = Path(d) / "jb.xml"
            jb.write_text(
                '<component name="CachedDictionaryState"><words/></component>',
                encoding="utf-8",
            )
            result = dictionary_read_result(
                Dictionary("jetbrains:IDEA", jb, DictionaryFormat.JETBRAINS),
            )
            self.assertEqual(result.status, ReadStatus.EMPTY)

            jb_ok = Path(d) / "jb_ok.xml"
            jb_ok.write_text(
                '<component name="CachedDictionaryState"><words><w>alpha</w></words></component>',
                encoding="utf-8",
            )
            ok_result = dictionary_read_result(
                Dictionary("jetbrains:IDEA", jb_ok, DictionaryFormat.JETBRAINS),
            )
            self.assertEqual(ok_result.status, ReadStatus.OK)
            self.assertIn("alpha", ok_result.words)

            with patch(
                "spell_sync.read_outcome.normalize_token",
                return_value="",
            ):
                junk = Path(d) / "junk.txt"
                junk.write_text("token\n", encoding="utf-8")
                text_result = dictionary_read_result(
                    Dictionary("t", junk, DictionaryFormat.TEXT),
                )
                self.assertEqual(text_result.status, ReadStatus.OK)
                self.assertEqual(text_result.words, frozenset())
