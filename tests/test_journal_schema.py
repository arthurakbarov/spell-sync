"""Journal schema field parsing and provenance validation."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

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
from spell_sync.push_transaction import txn_snapshot_root


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
            with self.assertRaises(JournalParseError) as raised:
                _validate_target_path("../secret/wordlist.txt")
            self.assertIn("unsafe", str(raised.exception).lower())
            self.assertNotIn("secret", str(raised.exception))
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
    unittest.main(verbosity=2)
