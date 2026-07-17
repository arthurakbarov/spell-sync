#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I/O, lint, and rollback resilience."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.io as io_mod
import spell_sync.lint as lint_mod
from spell_sync.exit_codes import ExitCode
from spell_sync.io import (
    read_chrome_words,
    read_json_words,
    read_text_words,
    write_chrome_words,
    write_json_words,
    write_text_words,
)


class TestLintResilience(unittest.TestCase):
    def test_missing_wordlist_returns_unreadable(self):
        missing = Path("/nonexistent/wordlist.txt")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = lint_mod.run_lint(missing)
        self.assertEqual(code, ExitCode.WORDLIST_UNREADABLE)
        self.assertIn("wordlist unavailable", buf.getvalue())

    def test_fix_aborts_when_write_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("alpha\n", encoding="utf-8")
            with patch.object(lint_mod, "write_text_words", return_value=False):
                code = lint_mod.run_lint(path, fix=True)
            self.assertEqual(code, ExitCode.PUSH_ABORT)


class TestIoResilience(unittest.TestCase):
    def test_json_read_respects_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = read_json_words(path, quiet=True)
            self.assertEqual(words, set())
            self.assertEqual(buf.getvalue(), "")

    def test_atomic_write_removes_temp_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            target.write_text("old\n", encoding="utf-8")
            with patch.object(io_mod.os, "replace", side_effect=OSError("replace fail")):
                with self.assertRaises(OSError):
                    io_mod.atomic_write(target, b"new\n")
            temps = list(Path(d).glob("*.tmp"))
            self.assertEqual(temps, [])

    def test_atomic_write_uses_unique_temp_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"

            temps: list[Path] = []
            real_mkstemp = io_mod.tempfile.mkstemp

            def spy_mkstemp(*args, **kwargs):
                fd, name = real_mkstemp(*args, **kwargs)
                temps.append(Path(name))
                return fd, name

            with patch.object(io_mod.tempfile, "mkstemp", side_effect=spy_mkstemp):
                io_mod.atomic_write(target, b"one\n")
                io_mod.atomic_write(target, b"two\n")

            self.assertEqual(len(temps), 2)
            self.assertTrue(all(p.suffix == ".tmp" for p in temps))
            self.assertNotEqual(temps[0], temps[1])

    def test_atomic_write_closes_fd_when_fdopen_fails(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"

            real_mkstemp = io_mod.tempfile.mkstemp

            def spy_mkstemp(*args, **kwargs):
                fd, name = real_mkstemp(*args, **kwargs)
                return fd, name

            with (
                patch.object(io_mod.tempfile, "mkstemp", side_effect=spy_mkstemp),
                patch.object(io_mod.os, "fdopen", side_effect=OSError("fdopen fail")),
                patch.object(io_mod.os, "close", wraps=io_mod.os.close) as close_spy,
            ):
                with self.assertRaises(OSError):
                    io_mod.atomic_write(target, b"x\n")
                close_spy.assert_called_once()


class TestRollbackResilience(unittest.TestCase):
    def test_rollback_logs_on_copy_failure(self):
        from spell_sync.push_transaction import (
            TargetWriteState,
            _FileBackup,
            _rollback_one_backup,
        )

        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "dict.txt"
            backup = Path(d) / "dict.bak"
            original.write_text("live\n", encoding="utf-8")
            backup.write_text("backup\n", encoding="utf-8")
            bak = _FileBackup(original, backup, True, "dict")
            bak.write_state = TargetWriteState.WRITE_STARTED
            buf = io.StringIO()
            with patch("spell_sync.push_transaction.shutil.copy2", side_effect=OSError("x")):
                with redirect_stdout(buf):
                    _rollback_one_backup(bak)
            self.assertIn("rollback failed", buf.getvalue())


class TestIoHelpers(unittest.TestCase):
    def test_is_path_readable_permission_denied(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blocked.txt"
            path.write_text("x", encoding="utf-8")
            side_effect = PermissionError(1, "denied")
            with patch("spell_sync.io.open", side_effect=side_effect):
                self.assertFalse(io_mod.is_path_readable(path))

    def test_is_path_readable_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "flaky.txt"
            path.write_text("x", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=OSError("stale handle")):
                self.assertFalse(io_mod.is_path_readable(path))

    def test_is_path_readable_missing_file(self):
        self.assertTrue(io_mod.is_path_readable("/no/such/file.txt"))

    def test_is_path_readable_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(io_mod.is_path_readable(d))

    def test_is_path_readable_directory_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(io_mod.os, "access", side_effect=OSError("denied")):
                self.assertFalse(io_mod.is_path_readable(d))

    def test_ensure_parent_dir_creates_nested(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "nested" / "dir" / "file.txt"
            io_mod.ensure_parent_dir(target)
            self.assertTrue(target.parent.is_dir())

    def test_detect_encoding_missing_file(self):
        self.assertIsNone(io_mod.detect_encoding("/missing.txt"))

    def test_detect_encoding_permission_denied(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blocked.txt"
            path.write_bytes(b"\xff\xfe")
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                self.assertIsNone(io_mod.detect_encoding(path))

    def test_detect_encoding_unknown_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "binary.bin"
            path.write_bytes(bytes(range(256)))
            self.assertIsNone(io_mod.detect_encoding(path))

    def test_physical_path_symlink_resolve_error(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "link.txt"
            link.symlink_to("missing-target.txt")
            with patch.object(Path, "resolve", side_effect=OSError("broken")):
                resolved = io_mod.physical_path(link)
            self.assertEqual(resolved, link)

    def test_atomic_write_backup_failure_still_writes(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            target.write_text("old\n", encoding="utf-8")
            with patch.object(io_mod.shutil, "copy2", side_effect=OSError("backup fail")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    io_mod.atomic_write(target, b"new\n")
            self.assertEqual(target.read_bytes(), b"new\n")
            self.assertIn("backup not created", buf.getvalue())

    def test_rotate_backup_chain_keep_one_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "dict.txt.bak"
            base.write_text("only\n", encoding="utf-8")
            io_mod.rotate_backup_chain(base, keep=1)
            self.assertEqual(base.read_text(encoding="utf-8"), "only\n")

    def test_rotate_backup_chain_shifts_numbered_files(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "dict.txt.bak"
            base.write_text("gen1\n", encoding="utf-8")
            Path(f"{base}.1").write_text("gen2\n", encoding="utf-8")
            io_mod.rotate_backup_chain(base, keep=3)
            self.assertFalse(base.exists())
            self.assertEqual(Path(f"{base}.1").read_text(encoding="utf-8"), "gen1\n")
            self.assertEqual(Path(f"{base}.2").read_text(encoding="utf-8"), "gen2\n")

    def test_atomic_write_rotates_before_backup(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            target.write_text("current\n", encoding="utf-8")
            backup = target.with_suffix(target.suffix + ".bak")
            backup.write_text("previous\n", encoding="utf-8")
            with patch.object(io_mod, "backup_keep_count", return_value=3):
                io_mod.atomic_write(target, b"next\n")
            self.assertEqual(target.read_bytes(), b"next\n")
            self.assertEqual(backup.read_text(encoding="utf-8"), "current\n")
            self.assertEqual(Path(f"{backup}.1").read_text(encoding="utf-8"), "previous\n")

    def test_atomic_write_skips_backup_when_keep_zero(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            target.write_text("old\n", encoding="utf-8")
            with patch.object(io_mod, "backup_keep_count", return_value=0):
                io_mod.atomic_write(target, b"new\n")
            self.assertEqual(target.read_bytes(), b"new\n")
            self.assertFalse(target.with_suffix(target.suffix + ".bak").exists())

    def test_read_text_skips_comment_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.txt"
            path.write_text("# header\nalpha\n# tail\n", encoding="utf-8")
            self.assertEqual(read_text_words(path, quiet=True), {"alpha"})

    def test_rotate_backup_chain_tolerates_rename_errors(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "dict.txt.bak"
            base.write_text("gen1\n", encoding="utf-8")
            with patch.object(Path, "rename", side_effect=OSError("busy")):
                io_mod.rotate_backup_chain(base, keep=3)
            self.assertTrue(base.exists())

    def test_atomic_write_temp_unlink_failure_still_raises(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            target.write_text("old\n", encoding="utf-8")

            def bad_unlink(*_args, **_kwargs):
                raise OSError("unlink fail")

            with (
                patch.object(io_mod.os, "replace", side_effect=OSError("replace fail")),
                patch.object(Path, "unlink", side_effect=bad_unlink),
            ):
                with self.assertRaises(OSError):
                    io_mod.atomic_write(target, b"new\n")


class TestIoFormats(unittest.TestCase):
    def test_read_text_logs_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dict.txt")
            write_text_words(path, ["alpha"], "utf-8", False, quiet=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = read_text_words(path, quiet=False)
            self.assertEqual(words, {"alpha"})
            self.assertIn("[read ]", buf.getvalue())

    def test_read_text_oserror_returns_empty_and_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dict.txt")
            Path(path).write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=OSError("stale handle")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_text_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (text)", buf.getvalue())

    def test_read_text_unicode_error_returns_empty_and_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dict.txt")
            Path(path).write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=UnicodeError("bad decode")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_text_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (text)", buf.getvalue())

    def test_write_text_failure(self):
        with patch.object(io_mod, "atomic_write", side_effect=PermissionError("nope")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_text_words("/x/dict.txt", ["a"], "utf-8", False, quiet=False)
            self.assertFalse(ok)
            self.assertIn("no write access", buf.getvalue())

    def test_read_json_success_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "prefs.json")
            write_json_words(path, ["alpha"], quiet=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = read_json_words(path, quiet=False)
            self.assertEqual(words, {"alpha"})
            self.assertIn("[read ]", buf.getvalue())

    def test_read_json_permission(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "prefs.json")
            Path(path).write_text('{"added_words": ["a"]}', encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=PermissionError("denied")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_json_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (json)", buf.getvalue())

    def test_read_json_corrupt_logs_and_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "prefs.json")
            Path(path).write_text("{not json", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = read_json_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (json)", buf.getvalue())

    def test_write_json_overwrites_corrupt_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertTrue(write_json_words(path, ["new"], quiet=True))
            self.assertIn("new", read_json_words(path, quiet=True))

    def test_write_json_failure(self):
        with patch.object(io_mod, "atomic_write", side_effect=OSError("fail")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_json_words("/x/prefs.json", ["a"], quiet=False)
            self.assertFalse(ok)

    def test_read_chrome_skips_checksum_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Custom Dictionary.txt")
            write_chrome_words(path, ["alpha", "beta"], quiet=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = read_chrome_words(path, quiet=False)
            self.assertEqual(words, {"alpha", "beta"})
            self.assertIn("[read ]", buf.getvalue())

    def test_read_chrome_permission(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Custom Dictionary.txt")
            Path(path).write_text("word\n", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=PermissionError("denied")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_chrome_words(path, quiet=False)
            self.assertEqual(words, set())

    def test_read_chrome_oserror_returns_empty_and_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Custom Dictionary.txt")
            Path(path).write_text("word\n", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=OSError("stale handle")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_chrome_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (chrome)", buf.getvalue())

    def test_write_chrome_failure(self):
        with patch.object(io_mod, "atomic_write", side_effect=OSError("fail")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_chrome_words("/x/chrome.txt", ["a"], quiet=False)
            self.assertFalse(ok)

    def test_write_json_success_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "prefs.json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_json_words(path, ["alpha"], quiet=False)
            self.assertTrue(ok)
            self.assertIn("[write]", buf.getvalue())

    def test_write_chrome_success_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "chrome.txt")
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_chrome_words(path, ["alpha"], quiet=False)
            self.assertTrue(ok)
            self.assertIn("[write]", buf.getvalue())

    def test_read_json_missing_file(self):
        self.assertEqual(read_json_words("/no/such.json", quiet=True), set())

    def test_read_chrome_missing_file(self):
        self.assertEqual(read_chrome_words("/no/such.txt", quiet=True), set())

    def test_text_payload_utf16_bom(self):
        data = io_mod._text_payload_bytes("a\n", "utf-16-le", bom=True)
        self.assertTrue(data.startswith(b"\xff\xfe"))

    def test_write_text_success_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dict.txt")
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = write_text_words(path, ["alpha"], "utf-8", False, quiet=False)
            self.assertTrue(ok)
            self.assertIn("[write]", buf.getvalue())

    def test_read_hunspell_permission_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "custom.dic")
            Path(path).write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.io.open", side_effect=PermissionError("denied")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = io_mod.read_hunspell_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (hunspell)", buf.getvalue())

    def test_read_jetbrains_unreadable_returns_empty(self):
        sample_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<application>
  <component name="CachedDictionaryState">
    <words><w>alpha</w></words>
  </component>
</application>
"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text(sample_xml, encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = io_mod.read_jetbrains_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("read failed (jetbrains)", buf.getvalue())

    def test_read_jetbrains_unreadable_quiet_does_not_force_output(self):
        sample_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<application>
  <component name="CachedDictionaryState">
    <words><w>alpha</w></words>
  </component>
</application>
"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text(sample_xml, encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = io_mod.read_jetbrains_words(path, quiet=True)
            self.assertEqual(words, set())
            self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
