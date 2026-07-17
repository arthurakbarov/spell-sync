#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-process operation lock."""

from __future__ import annotations

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
        info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
        lock_path = lock_path_for_wordlist(wordlist)
        with patch(
            "spell_sync.command_helpers.acquire_operation_lock",
            side_effect=OperationLocked(info, lock_path),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(json_output=True, wordlist=str(wordlist)))
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "operation_locked")
        self.assertEqual(payload["schema_version"], 1)

    def test_operation_lock_scope_human(self):
        wordlist = Path(tempfile.mkdtemp()) / "wordlist.txt"
        wordlist.write_text("alpha\n", encoding="utf-8")
        info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
        lock_path = lock_path_for_wordlist(wordlist)
        with patch(
            "spell_sync.command_helpers.acquire_operation_lock",
            side_effect=OperationLocked(info, lock_path),
        ):
            code = commands.cmd_push(CliOptions(wordlist=str(wordlist), yes=True))
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_read_lock_info_invalid_json(self):
        from spell_sync.operation_lock import _read_lock_info

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".spell-sync.lock"
            path.write_text("{bad", encoding="utf-8")
            self.assertIsNone(_read_lock_info(path))

    def test_read_lock_info_valid_json(self):
        from spell_sync.operation_lock import OperationLockInfo, _read_lock_info

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".spell-sync.lock"
            path.write_text(
                json.dumps(
                    {
                        "pid": 42,
                        "started": "2026-01-01T00:00:00+00:00",
                        "command": "push",
                        "wordlist": "/tmp/wordlist.txt",
                    }
                ),
                encoding="utf-8",
            )
            info = _read_lock_info(path)
            self.assertEqual(
                info,
                OperationLockInfo(42, "2026-01-01T00:00:00+00:00", "push", "/tmp/wordlist.txt"),
            )

    def test_pid_alive_zero(self):
        from spell_sync.operation_lock import _pid_alive

        self.assertFalse(_pid_alive(0))

    def test_pid_alive_permission_error(self):
        if sys.platform == "win32":
            self.skipTest("Windows uses OpenProcess, not os.kill")
        from spell_sync.operation_lock import _pid_alive

        with patch("spell_sync.operation_lock.os.kill", side_effect=PermissionError):
            self.assertTrue(_pid_alive(12345))

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
                patch("spell_sync.operation_lock._read_lock_info", return_value=None),
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
            with patch("spell_sync.operation_lock.os.close", side_effect=OSError("nope")):
                with acquire_operation_lock(wordlist, "push"):
                    pass

    def test_pid_alive_process_lookup_error(self):
        from spell_sync.operation_lock import _pid_alive

        with patch("spell_sync.operation_lock.os.kill", side_effect=ProcessLookupError):
            self.assertFalse(_pid_alive(12345))

    def test_release_fd_oserror_unix(self):
        if sys.platform == "win32":
            self.skipTest("fcntl is Unix-only")
        from spell_sync.operation_lock import _release_fd

        with patch("spell_sync.operation_lock.sys.platform", "darwin"):
            with patch("fcntl.flock", side_effect=OSError("nope")):
                _release_fd(0)


class TestOperationLockWin32(unittest.TestCase):
    def test_win32_pid_alive_and_lock(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_NBLCK = 1
        msvcrt.LK_UNLCK = 0
        mock_ctypes = mock.MagicMock()
        mock_ctypes.windll.kernel32.OpenProcess.return_value = 1
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt, "ctypes": mock_ctypes}),
        ):
            from spell_sync.operation_lock import _pid_alive

            self.assertTrue(_pid_alive(100))
            self.assertFalse(_pid_alive(0))
            with tempfile.TemporaryDirectory() as d:
                wordlist = Path(d) / "wordlist.txt"
                wordlist.write_text("alpha\n", encoding="utf-8")
                with acquire_operation_lock(wordlist, "push"):
                    pass
        self.assertTrue(msvcrt.locking.called)

    def test_win32_pid_not_alive(self):
        mock_ctypes = mock.MagicMock()
        mock_ctypes.windll.kernel32.OpenProcess.return_value = 0
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch.dict(sys.modules, {"ctypes": mock_ctypes}),
        ):
            from spell_sync.operation_lock import _pid_alive

            self.assertFalse(_pid_alive(100))

    def test_win32_lock_contention(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_NBLCK = 1
        msvcrt.locking.side_effect = OSError("locked")
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt}),
        ):
            with tempfile.TemporaryDirectory() as d:
                wordlist = Path(d) / "wordlist.txt"
                wordlist.write_text("alpha\n", encoding="utf-8")
                with self.assertRaises(OperationLocked):
                    with acquire_operation_lock(wordlist, "pull"):
                        pass

    def test_win32_release_oserror(self):
        msvcrt = mock.MagicMock()
        msvcrt.LK_UNLCK = 0
        msvcrt.locking.side_effect = OSError("unlock failed")
        with (
            patch("spell_sync.operation_lock.sys.platform", "win32"),
            patch.dict(sys.modules, {"msvcrt": msvcrt}),
        ):
            from spell_sync.operation_lock import _release_fd

            _release_fd(0)
