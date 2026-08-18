"""Cross-process operation lock."""

import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.operation_lock import (
    OperationLocked,
    OperationLockInfo,
    acquire_operation_lock,
    lock_path_for_wordlist,
    read_active_operation_lock,
)


class TestOperationLock(unittest.TestCase):
    def test_second_holder_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with acquire_operation_lock(wordlist, "push"):
                with self.assertRaises(OperationLocked):
                    with acquire_operation_lock(wordlist, "pull"):
                        pass

    def test_lock_released_after_context(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with acquire_operation_lock(wordlist, "push"):
                pass
            with acquire_operation_lock(wordlist, "pull"):
                pass

    def test_subprocess_blocks_while_parent_holds_lock(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
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
                proc = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=d,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            self.assertEqual(proc.returncode, 17)

    def test_lock_path_next_to_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "nested" / "wordlist.txt"
            wordlist.parent.mkdir(parents=True)
            wordlist.write_text("a\n", encoding="utf-8")
            self.assertEqual(
                lock_path_for_wordlist(wordlist).resolve(),
                (wordlist.parent / ".spell-sync.lock").resolve(),
            )

    def test_operation_lock_scope_json(self):
        wordlist = Path(tempfile.mkdtemp()) / "wordlist.txt"
        wordlist.write_text("alpha\n", encoding="utf-8")
        (wordlist.parent / "spell-sync.toml").write_text(
            "[dictionaries]\n"
            "editors = false\nchrome = false\nedge = false\nbrave = false\n"
            "vivaldi = false\nfirefox = false\nneovim = false\nsublime = false\njetbrains = false\n"
            "hunspell = false\nobsidian = false\nlibreoffice = false\n",
            encoding="utf-8",
        )
        info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "pull", str(wordlist))
        lock_path = lock_path_for_wordlist(wordlist)
        with patch(
            "spell_sync.mutation_guards.acquire_operation_lock",
            side_effect=OperationLocked(info, lock_path),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(CliOptions(json_output=True, wordlist=str(wordlist)))
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "operation_locked")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "pull")

    def test_operation_lock_scope_human(self):
        wordlist = Path(tempfile.mkdtemp()) / "wordlist.txt"
        wordlist.write_text("alpha\n", encoding="utf-8")
        info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
        lock_path = lock_path_for_wordlist(wordlist)
        with patch(
            "spell_sync.mutation_guards.acquire_operation_lock",
            side_effect=OperationLocked(info, lock_path),
        ):
            code = commands.cmd_push(CliOptions(wordlist=str(wordlist), yes=True))
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_stale_metadata_overwritten_when_flock_acquired(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = lock_path_for_wordlist(wordlist)
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "started": "2026-01-01T00:00:00+00:00",
                        "command": "push",
                        "wordlist": str(wordlist),
                    }
                ),
                encoding="utf-8",
            )
            with acquire_operation_lock(wordlist, "pull") as info:
                self.assertEqual(info.command, "pull")
                self.assertEqual(info.pid, os.getpid())

    def test_acquire_blocked_when_kernel_lock_held(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.operation_lock._try_acquire_fd", return_value=False):
                with self.assertRaises(OperationLocked):
                    with acquire_operation_lock(wordlist, "push"):
                        pass

    def test_acquire_raises_unknown_lock_without_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with (
                patch("spell_sync.operation_lock._try_acquire_fd", return_value=False),
                patch("spell_sync.operation_lock._read_lock_info_fd", return_value=None),
            ):
                with self.assertRaises(OperationLocked) as ctx:
                    with acquire_operation_lock(wordlist, "push"):
                        pass
                self.assertEqual(ctx.exception.info.pid, 0)

    def test_close_fd_oserror(self):
        if sys.platform == "win32":
            self.skipTest("Windows keeps lock files open when os.close fails")
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.operation_lock._close_lock_fd", side_effect=OSError("nope")):
                with acquire_operation_lock(wordlist, "push"):
                    pass

    def test_release_fd_oserror_unix(self):
        if sys.platform == "win32":
            self.skipTest("fcntl is Unix-only")
        from spell_sync.operation_lock import _release_fd

        with patch("spell_sync.operation_lock.sys.platform", "darwin"):
            with patch("fcntl.flock", side_effect=OSError("nope")):
                _release_fd(0)


class TestOperationLockWin32(unittest.TestCase):
    def test_win32_lock_acquire(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_NBLCK = 1
        msvcrt.LK_UNLCK = 0
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch("spell_sync.trusted_internal_fs.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt}),
        ):
            with tempfile.TemporaryDirectory() as d:
                wordlist = Path(d) / "wordlist.txt"
                wordlist.write_text("alpha\n", encoding="utf-8")
                lock_path = lock_path_for_wordlist(wordlist)
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
                with patch(
                    "spell_sync.operation_lock.open_trusted_regular_file",
                    return_value=lock_fd,
                ):
                    with acquire_operation_lock(wordlist, "push"):
                        pass
        self.assertTrue(msvcrt.locking.called)

    def test_win32_lock_contention(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_NBLCK = 1
        msvcrt.locking.side_effect = OSError("locked")
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch("spell_sync.trusted_internal_fs.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt}),
        ):
            with tempfile.TemporaryDirectory() as d:
                wordlist = Path(d) / "wordlist.txt"
                wordlist.write_text("alpha\n", encoding="utf-8")
                lock_path = lock_path_for_wordlist(wordlist)
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
                with patch(
                    "spell_sync.operation_lock.open_trusted_regular_file",
                    return_value=lock_fd,
                ):
                    with self.assertRaises(OperationLocked):
                        with acquire_operation_lock(wordlist, "pull"):
                            pass

    def test_win32_release_oserror(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_UNLCK = 0
        msvcrt.locking.side_effect = OSError("unlock failed")
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch("spell_sync.trusted_internal_fs.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt}),
        ):
            from spell_sync.operation_lock import _release_fd

            _release_fd(0)

    def test_read_active_operation_lock_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = lock_path_for_wordlist(wordlist)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("not-json", encoding="utf-8")
            # Flock free → corrupt metadata must not block the dashboard.
            self.assertIsNone(read_active_operation_lock(wordlist))

    def test_read_active_operation_lock_stale_pid(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = lock_path_for_wordlist(wordlist)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "pid": 999_999_999,
                "started": "2020-01-01T00:00:00+00:00",
                "command": "push",
                "wordlist": str(wordlist),
            }
            lock_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(read_active_operation_lock(wordlist))

    def test_read_active_operation_lock_absent(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            self.assertIsNone(read_active_operation_lock(wordlist))

    def test_read_active_operation_lock_ignores_self_pid_after_release(self):
        """Released lock still names this PID; flock is free → not active."""
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with acquire_operation_lock(wordlist, "push"):
                pass
            # Metadata still lists os.getpid(); dashboard must not block.
            self.assertIsNone(read_active_operation_lock(wordlist))

    def test_read_active_operation_lock_held_by_other_process(self):
        if sys.platform == "win32":
            self.skipTest("subprocess flock probe coverage is Unix-focused")
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            script = textwrap.dedent(
                f"""
                import sys, time
                from pathlib import Path
                from spell_sync.operation_lock import acquire_operation_lock
                with acquire_operation_lock(Path({str(wordlist)!r}), "push"):
                    sys.stdout.write("ready\\n")
                    sys.stdout.flush()
                    time.sleep(30)
                """
            )
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
            proc = subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=d,
                env=env,
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                assert proc.stdout is not None
                line = proc.stdout.readline()
                self.assertEqual(line.strip(), "ready")
                info = read_active_operation_lock(wordlist)
                self.assertIsNotNone(info)
                assert info is not None
                self.assertEqual(info.command, "push")
                self.assertEqual(info.pid, proc.pid)
            finally:
                proc.kill()
                proc.wait(timeout=5)
