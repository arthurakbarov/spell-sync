"""Line and branch coverage for spell_sync.trusted_internal_fs and secure_artifacts gaps."""

from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.secure_artifacts import (
    SecureArtifactError,
    _fchmod_private,
    _fsync_directory,
    _reject_unsafe_component,
    _relative_under_root,
    atomic_write_trusted_file,
    copy_trusted_snapshot_file,
    create_trusted_snapshot_file,
    ensure_trusted_directory,
    read_trusted_regular_file,
    remove_trusted_tree,
    trusted_project_root,
)
from spell_sync.trusted_internal_fs import (
    TrustedDirectory,
    TrustedFile,
    TrustedFsError,
    _check_dir_mode,
    _check_file_mode,
    _check_posix_owner,
    _dir_fd_supported,
    _fsync_directory_fd,
    _fsync_fd,
    _posix_open_at,
    relative_components,
    set_open_boundary_hook,
    validate_relative_name,
)


class TestTrustedInternalFsCoverage(unittest.TestCase):
    def test_validate_relative_name_rejects(self) -> None:
        for bad in ("", ".", "..", "a/b", "/abs"):
            with self.subTest(name=bad):
                with self.assertRaises(TrustedFsError) as ctx:
                    validate_relative_name(bad)
                self.assertEqual(ctx.exception.code, "invalid_name")
        with patch.object(Path, "anchor", new_callable=lambda: property(lambda self: "C:")):
            with patch(
                "spell_sync.trusted_internal_fs.os.sep",
                "\\",
            ):
                with patch(
                    "spell_sync.trusted_internal_fs.os.altsep",
                    "/",
                ):
                    with self.assertRaises(TrustedFsError) as ctx:
                        validate_relative_name("C:foo")
                    self.assertEqual(ctx.exception.code, "invalid_name")

    def test_relative_components_root_and_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(TrustedFsError) as ctx:
                relative_components(root.resolve(), root)
            self.assertEqual(ctx.exception.code, "outside_trusted_root")
            outside = Path(tmp).parent / "outside" / "x"
            with self.assertRaises(TrustedFsError):
                relative_components(outside, root)

    def test_dir_fd_supported(self) -> None:
        with patch.object(sys, "platform", "win32"):
            self.assertTrue(_dir_fd_supported())
        with patch(
            "spell_sync.trusted_internal_fs.os.open",
            side_effect=OSError(errno.EPERM, "denied"),
        ):
            self.assertFalse(_dir_fd_supported())

    def test_fchmod_private_fd_on_unix(self) -> None:
        import spell_sync.trusted_internal_fs as tif

        with tempfile.TemporaryDirectory() as tmp:
            dir_fd = os.open(tmp, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                with tempfile.NamedTemporaryFile(dir=tmp, delete=False) as temp:
                    file_fd = temp.fileno()
                    tif._fchmod_private_fd(file_fd)
                tif._fchmod_private_dir_fd(dir_fd)
            finally:
                os.close(dir_fd)

    def test_fchmod_win32_noop(self) -> None:
        import spell_sync.trusted_internal_fs as tif

        with patch.object(tif.sys, "platform", "win32"):
            tif._fchmod_private_fd(1)
            tif._fchmod_private_dir_fd(1)

    def test_fchmod_and_fsync_helpers(self) -> None:
        with patch("spell_sync.trusted_internal_fs.sys.platform", "win32"):
            _fsync_directory_fd(1)
            _check_posix_owner(type("ST", (), {"st_uid": 999})())
            _check_dir_mode(
                type("ST", (), {"st_mode": stat.S_IFDIR | 0o777})(),
                harden=False,
                fd=1,
            )
            _check_file_mode(type("ST", (), {"st_mode": stat.S_IFREG | 0o644})(), fd=1)
        with patch(
            "spell_sync.trusted_internal_fs.os.fsync",
            side_effect=OSError(errno.ENOSYS, "nosys"),
        ):
            _fsync_fd(1)
        with patch(
            "spell_sync.trusted_internal_fs.os.fsync",
            side_effect=OSError(errno.EIO, "io"),
        ):
            with self.assertRaises(OSError):
                _fsync_fd(1)

    def test_flush_file_buffers_failure(self) -> None:
        from spell_sync.trusted_internal_fs import _flush_file

        fake_msvcrt = MagicMock()
        fake_msvcrt.get_osfhandle.return_value = 1
        fake_ctypes = MagicMock()
        fake_ctypes.windll.kernel32.FlushFileBuffers.return_value = 0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "out"
            fd = os.open(target, os.O_CREAT | os.O_RDWR)
            try:
                with patch.object(sys, "platform", "win32"):
                    with patch.dict(sys.modules, {"msvcrt": fake_msvcrt, "ctypes": fake_ctypes}):
                        with patch(
                            "spell_sync.trusted_internal_fs.os.fsync",
                            side_effect=OSError(errno.EINVAL, "bad"),
                        ):
                            _flush_file(fd)
            finally:
                os.close(fd)

    def test_posix_open_at_unsupported(self) -> None:
        with patch(
            "spell_sync.trusted_internal_fs._dir_fd_supported",
            return_value=False,
        ):
            with self.assertRaises(TrustedFsError) as ctx:
                _posix_open_at(0, "x", os.O_RDONLY)
            self.assertEqual(ctx.exception.code, "unsupported_platform")

    def test_trusted_file_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            self.assertGreaterEqual(trusted.fd, 0)
            with trusted.open_regular_file("data", create=True) as handle:
                handle.write_all(b"hello")
                self.assertEqual(handle.read_all(), b"hello")
                handle.sync()
                self.assertGreaterEqual(handle.fd, 0)
                self.assertEqual(handle.presentation_path, root / "data")
                handle.close()
                handle.close()
            with trusted as ctx:
                self.assertIs(ctx, trusted)
            trusted.close()
            trusted.close()

    def test_open_root_not_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocker = root / "blocker"
            blocker.write_text("x", encoding="utf-8")
            with patch("spell_sync.trusted_internal_fs.os.open", return_value=55):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    return_value=type("ST", (), {"st_mode": stat.S_IFREG | 0o644})(),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            TrustedDirectory.open_root(blocker)
                        self.assertEqual(ctx.exception.code, "not_a_directory")
                        close_mock.assert_any_call(55)

    def test_open_root_fstat_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("spell_sync.trusted_internal_fs.os.open", return_value=99):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    side_effect=OSError(errno.EIO, "io"),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            TrustedDirectory.open_root(root)
                        self.assertEqual(ctx.exception.code, "fstat_failed")
                        close_mock.assert_any_call(99)

    def test_from_components_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "first").mkdir()
            with patch.object(
                TrustedDirectory,
                "open_child_directory",
                side_effect=TrustedFsError("missing_directory", "missing"),
            ):
                with self.assertRaises(TrustedFsError):
                    TrustedDirectory.from_components(root, ("first", "second"))

    def test_open_child_directory_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            with self.assertRaises(TrustedFsError) as ctx:
                trusted.open_child_directory("missing")
            self.assertEqual(ctx.exception.code, "missing_directory")
            file_path = root / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(TrustedFsError) as ctx:
                trusted.open_child_directory("file.txt")
            self.assertEqual(ctx.exception.code, "not_a_directory")
            with patch(
                "spell_sync.trusted_internal_fs._posix_open_at",
                side_effect=OSError(errno.EACCES, "denied"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.open_child_directory("file.txt")
                self.assertEqual(ctx.exception.code, "open_failed")
            link = root / "linkdir"
            link.symlink_to(root, target_is_directory=True)
            with patch("spell_sync.trusted_internal_fs._posix_open_at", return_value=79):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    return_value=type("ST", (), {"st_mode": stat.S_IFLNK})(),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            trusted.open_child_directory("linkdir")
                        self.assertEqual(ctx.exception.code, "reparse_point")
                        close_mock.assert_any_call(79)
            with patch("spell_sync.trusted_internal_fs._posix_open_at", return_value=88):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    side_effect=OSError(errno.EIO, "io"),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            trusted.open_child_directory("file.txt")
                        self.assertEqual(ctx.exception.code, "fstat_failed")
                        close_mock.assert_any_call(88)
            trusted.close()

    def test_check_dir_mode_branches(self) -> None:
        st = type(
            "ST",
            (),
            {"st_mode": stat.S_IFDIR | 0o777, "st_uid": os.geteuid()},
        )()
        with tempfile.TemporaryDirectory() as tmp:
            fd = os.open(tmp, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                with patch(
                    "spell_sync.trusted_internal_fs.os.fchmod",
                    side_effect=OSError(errno.EPERM, "perm"),
                ):
                    with self.assertRaises(TrustedFsError) as ctx:
                        _check_dir_mode(st, harden=True, fd=fd)
                    self.assertEqual(ctx.exception.code, "mode_harden_failed")
                with patch("spell_sync.trusted_internal_fs.os.fchmod"):
                    with patch(
                        "spell_sync.trusted_internal_fs.os.fstat",
                        return_value=type(
                            "ST2",
                            (),
                            {"st_mode": stat.S_IFDIR | 0o755},
                        )(),
                    ):
                        with self.assertRaises(TrustedFsError) as ctx:
                            _check_dir_mode(st, harden=True, fd=fd)
                        self.assertEqual(ctx.exception.code, "insecure_directory_mode")
                with self.assertRaises(TrustedFsError) as ctx:
                    _check_dir_mode(st, harden=False, fd=fd)
                self.assertEqual(ctx.exception.code, "insecure_directory_mode")
                good = type("ST3", (), {"st_mode": stat.S_IFDIR | 0o700})()
                _check_dir_mode(good, harden=True, fd=fd)
            finally:
                os.close(fd)

    def test_check_file_mode_fchmod_failure(self) -> None:
        st = type("ST", (), {"st_mode": stat.S_IFREG | 0o644})()
        with patch(
            "spell_sync.trusted_internal_fs.os.fchmod",
            side_effect=OSError(errno.EPERM, "perm"),
        ):
            with self.assertRaises(TrustedFsError) as ctx:
                _check_file_mode(st, fd=1)
            self.assertEqual(ctx.exception.code, "mode_harden_failed")

    def test_check_posix_owner_rejects(self) -> None:
        st = type("ST", (), {"st_uid": os.geteuid() + 1})()
        with self.assertRaises(TrustedFsError) as ctx:
            _check_posix_owner(st)
        self.assertEqual(ctx.exception.code, "wrong_owner")

    def test_ensure_child_directory_eexist_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            (root / "exists").mkdir()

            class ExistError(OSError):
                errno = errno.EEXIST

            with patch(
                "spell_sync.trusted_internal_fs.os.mkdir",
                side_effect=ExistError("exists"),
            ):
                child = trusted.ensure_child_directory("exists")
                child.close()
            trusted.close()

    def test_open_child_directory_not_directory_fstat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            (root / "node").write_text("x", encoding="utf-8")
            with patch("spell_sync.trusted_internal_fs._posix_open_at", return_value=80):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    return_value=type(
                        "ST",
                        (),
                        {"st_mode": stat.S_IFREG | 0o644, "st_uid": os.geteuid()},
                    )(),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            trusted.open_child_directory("node")
                        self.assertEqual(ctx.exception.code, "not_a_directory")
                        close_mock.assert_any_call(80)
            trusted.close()

    def test_open_regular_file_fstat_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            target = root / "target"
            target.write_text("x", encoding="utf-8")
            with patch("spell_sync.trusted_internal_fs._posix_open_at", return_value=77):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    side_effect=OSError(errno.EIO, "io"),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            trusted.open_regular_file("target")
                        self.assertEqual(ctx.exception.code, "fstat_failed")
                        close_mock.assert_any_call(77)
            with patch("spell_sync.trusted_internal_fs._posix_open_at", return_value=78):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    return_value=type("ST", (), {"st_mode": stat.S_IFLNK})(),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(TrustedFsError) as ctx:
                            trusted.open_regular_file("target")
                        self.assertEqual(ctx.exception.code, "reparse_point")
                        close_mock.assert_any_call(78)
            fifo = root / "fifo"
            try:
                os.mkfifo(fifo)
            except OSError, AttributeError:
                self.skipTest("mkfifo unavailable")
            with self.assertRaises(TrustedFsError) as ctx:
                trusted.open_regular_file("fifo")
            self.assertEqual(ctx.exception.code, "not_a_file")
            trusted.close()

    def test_create_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            handle, temp_name = trusted.create_temp_file("pre", ".tmp")
            self.assertTrue(temp_name.startswith("pre"))
            self.assertTrue(temp_name.endswith(".tmp"))
            handle.close()
            trusted.close()

    def test_atomic_replace_over_existing_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            final = root / "final"
            final.write_text("old", encoding="utf-8")
            with trusted.open_regular_file("temp", create=True) as temp:
                temp.write_all(b"new")
            trusted.atomic_replace("temp", "final")
            self.assertEqual(final.read_bytes(), b"new")
            trusted.close()

    def test_atomic_replace_rejects_existing_directory_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            with trusted.open_regular_file("temp", create=True) as temp:
                temp.write_all(b"x")
            (root / "finaldir").mkdir()
            with self.assertRaises(TrustedFsError) as ctx:
                trusted.atomic_replace("temp", "finaldir")
            self.assertEqual(ctx.exception.code, "not_a_file")
            trusted.close()

    def test_atomic_replace_stat_and_symlink_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            with trusted.open_regular_file("temp", create=True) as temp:
                temp.write_all(b"x")
            with patch(
                "spell_sync.trusted_internal_fs.os.stat",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.atomic_replace("temp", "final")
                self.assertEqual(ctx.exception.code, "stat_failed")
            final = root / "final"
            final.write_text("old", encoding="utf-8")
            with trusted.open_regular_file("temp2", create=True) as temp2:
                temp2.write_all(b"new")
            with patch(
                "spell_sync.trusted_internal_fs.os.stat",
                return_value=type("ST", (), {"st_mode": stat.S_IFLNK})(),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.atomic_replace("temp2", "final")
                self.assertEqual(ctx.exception.code, "reparse_point")
            trusted.close()

    def test_unlink_and_rmdir_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            victim = root / "victim.txt"
            victim.write_text("x", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(victim)
            with self.assertRaises(TrustedFsError):
                trusted.unlink_entry("link.txt")
            (root / "dir").mkdir()
            with self.assertRaises(TrustedFsError):
                trusted.unlink_entry("dir")
            with patch(
                "spell_sync.trusted_internal_fs.os.stat",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.unlink_entry("victim.txt")
                self.assertEqual(ctx.exception.code, "stat_failed")
            with patch(
                "spell_sync.trusted_internal_fs.os.unlink",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.unlink_entry("victim.txt")
                self.assertEqual(ctx.exception.code, "unlink_failed")
            trusted.unlink_entry("missing.txt")
            link_dir = root / "linkdir"
            link_dir.symlink_to(root, target_is_directory=True)
            with self.assertRaises(TrustedFsError):
                trusted.remove_child_directory("linkdir")
            file_path = root / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(TrustedFsError):
                trusted.remove_child_directory("file.txt")
            with patch(
                "spell_sync.trusted_internal_fs.os.stat",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.remove_child_directory("dir")
                self.assertEqual(ctx.exception.code, "stat_failed")
            trusted.remove_child_directory("missing")
            with patch(
                "spell_sync.trusted_internal_fs.os.rmdir",
                side_effect=OSError(errno.EBUSY, "busy"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.remove_child_directory("dir")
                self.assertEqual(ctx.exception.code, "rmdir_failed")
            trusted.close()

    def test_remove_owned_tree_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            tree = root / "tree"
            tree.mkdir()
            (tree / "child.txt").write_text("x", encoding="utf-8")
            sub = trusted.open_child_directory("tree")
            with patch(
                "spell_sync.trusted_internal_fs.os.stat",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    sub.remove_owned_tree()
                self.assertEqual(ctx.exception.code, "stat_failed")
            sub.close()
            tree = root / "tree2"
            tree.mkdir()
            (tree / "nested").mkdir()
            sub = trusted.open_child_directory("tree2")
            with patch(
                "spell_sync.trusted_internal_fs.os.rmdir",
                side_effect=OSError(errno.EBUSY, "busy"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    sub.remove_owned_tree()
                self.assertEqual(ctx.exception.code, "rmdir_failed")
            sub.close()
            tree = root / "tree3"
            tree.mkdir()
            (tree / "f.txt").write_text("x", encoding="utf-8")
            sub = trusted.open_child_directory("tree3")
            with patch(
                "spell_sync.trusted_internal_fs.os.unlink",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    sub.remove_owned_tree()
                self.assertEqual(ctx.exception.code, "unlink_failed")
            sub.close()
            try:
                fifo = root / "tree4"
                fifo.mkdir()
                os.mkfifo(fifo / "pipe")
            except OSError, AttributeError:
                self.skipTest("mkfifo unavailable")
            sub = trusted.open_child_directory("tree4")
            with self.assertRaises(TrustedFsError) as ctx:
                sub.remove_owned_tree()
            self.assertEqual(ctx.exception.code, "unexpected_path_type")
            sub.close()
            trusted.close()

    def test_copy_regular_file_partial_write_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            source = root / "source.txt"
            source.write_text("payload", encoding="utf-8")
            with patch(
                "spell_sync.trusted_internal_fs.os.write",
                return_value=0,
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.copy_regular_file_from_path("snap", source)
                self.assertEqual(ctx.exception.code, "partial_write")
            with patch("builtins.open", side_effect=OSError(errno.EIO, "read")):
                with patch.object(
                    TrustedDirectory,
                    "unlink_entry",
                    side_effect=TrustedFsError("unlink_failed", "fail"),
                ):
                    with self.assertRaises(OSError):
                        trusted.copy_regular_file_from_path("snap2", source)
            trusted.close()

    def test_verify_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            txn = project / ".spell-sync.txn"
            txn.mkdir(parents=True)

            def hook(phase: str, name: str) -> None:
                if phase == "before_file_open" and name == "file.json":
                    backup = project / ".spell-sync.txn.bak"
                    txn.rename(backup)
                    txn.mkdir()

            set_open_boundary_hook(hook)
            try:
                trusted = TrustedDirectory.from_components(project, (".spell-sync.txn",))
                with self.assertRaises(TrustedFsError) as ctx:
                    trusted.open_regular_file("file.json", create=True)
                self.assertEqual(ctx.exception.code, "identity_mismatch")
                trusted.close()
            finally:
                set_open_boundary_hook(None)

    def test_verify_identity_open_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            parent = TrustedDirectory.open_root(root)
            child = parent.open_child_directory("sub")
            with patch(
                "spell_sync.trusted_internal_fs._posix_open_at",
                side_effect=OSError(errno.ENOENT, "missing"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    child.open_regular_file("x", create=True)
                self.assertEqual(ctx.exception.code, "identity_mismatch")
            child.close()
            parent.close()

    def test_open_regular_file_rejects_hard_link_when_mutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            original = root / "original"
            original.write_text("x", encoding="utf-8")
            os.link(original, root / "linked")
            with self.assertRaises(TrustedFsError) as ctx:
                trusted.open_regular_file("linked", mutable=True)
            self.assertEqual(ctx.exception.code, "hard_link")
            trusted.close()

    def test_copy_regular_file_multichunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted = TrustedDirectory.open_root(root)
            source = root / "source.txt"
            source.write_bytes(b"x" * 70000)
            handle = trusted.copy_regular_file_from_path("snap", source)
            try:
                self.assertEqual(handle.read_all(), source.read_bytes())
            finally:
                handle.close()
            trusted.close()

    def test_verify_identity_fstat_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            parent = TrustedDirectory.open_root(root)
            child = parent.open_child_directory("sub")
            with patch(
                "spell_sync.trusted_internal_fs.os.fstat",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with self.assertRaises(TrustedFsError) as ctx:
                    child.open_regular_file("x", create=True)
                self.assertEqual(ctx.exception.code, "fstat_failed")
            child.close()
            parent.close()

    def test_win32_dispatch_branches(self) -> None:
        with patch("spell_sync.trusted_internal_fs.sys.platform", "win32"):
            root = Path(tempfile.mkdtemp())
            try:
                fake_dir = TrustedDirectory(-1, root)
                with patch(
                    "spell_sync.trusted_internal_fs._win_open_root",
                    return_value=fake_dir,
                ):
                    opened = TrustedDirectory.open_root(root)
                    self.assertIs(opened, fake_dir)
                with patch(
                    "spell_sync.trusted_internal_fs._win_open_child_directory",
                    return_value=fake_dir,
                ):
                    fake_dir.open_child_directory("x")
                with patch(
                    "spell_sync.trusted_internal_fs._win_ensure_child_directory",
                    return_value=fake_dir,
                ):
                    fake_dir.ensure_child_directory("x")
                fake_file = TrustedFile(-1, fake_dir, "f")
                with patch(
                    "spell_sync.trusted_internal_fs._win_open_regular_file",
                    return_value=fake_file,
                ):
                    fake_dir.open_regular_file("f")
                with patch("spell_sync.trusted_internal_fs._win_atomic_replace"):
                    fake_dir.atomic_replace("a", "b")
                with patch("spell_sync.trusted_internal_fs._win_unlink_entry"):
                    fake_dir.unlink_entry("a")
                with patch("spell_sync.trusted_internal_fs._win_remove_child_directory"):
                    fake_dir.remove_child_directory("a")
                with patch("spell_sync.trusted_internal_fs._win_remove_owned_tree"):
                    fake_dir.remove_owned_tree()
            finally:
                root.rmdir()


class TestSecureArtifactsRemainingGaps(unittest.TestCase):
    def _root(self, tmp: str) -> tuple[Path, Path]:
        wordlist = Path(tmp) / "wordlist.txt"
        wordlist.write_text("a\n", encoding="utf-8")
        return wordlist, trusted_project_root(wordlist)

    def test_directory_at_maps_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._root(tmp)
            snap_dir = root / ".spell-sync.txn" / "tid"
            with patch(
                "spell_sync.secure_artifacts.TrustedDirectory.from_components",
                side_effect=TrustedFsError("missing_directory", "missing"),
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    copy_trusted_snapshot_file(
                        snap_dir,
                        root=root,
                        base_name="dict",
                        source=wordlist,
                    )
                self.assertEqual(ctx.exception.code, "missing_directory")

    def test_atomic_write_cleanup_secure_error_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, root = self._root(tmp)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.secure_artifacts.os.replace",
                side_effect=OSError(errno.EIO, "io"),
            ):
                with patch(
                    "spell_sync.secure_artifacts.TrustedDirectory.unlink_entry",
                    side_effect=SecureArtifactError("unlink_failed", "fail"),
                ):
                    with self.assertRaises(SecureArtifactError):
                        atomic_write_trusted_file(target, b"x", root=root)

    def test_remove_tree_from_components_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, root = self._root(tmp)
            nested = root / "a" / "b"
            ensure_trusted_directory(nested, root=root)
            with patch(
                "spell_sync.secure_artifacts.TrustedDirectory.from_components",
                side_effect=TrustedFsError("open_failed", "fail"),
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    remove_trusted_tree(nested, root=root)
                self.assertEqual(ctx.exception.code, "open_failed")

    def test_create_snapshot_error_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._root(tmp)
            txn = root / ".spell-sync.txn" / "tid"
            txn.mkdir(parents=True)
            with patch(
                "spell_sync.secure_artifacts.TrustedDirectory.open_regular_file",
                side_effect=TrustedFsError("open_failed", "fail"),
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    create_trusted_snapshot_file(txn, root=root, base_name="dict")
                self.assertEqual(ctx.exception.code, "open_failed")

    def test_fchmod_private_win32(self) -> None:
        with patch.object(sys, "platform", "win32"):
            _fchmod_private(1)

    def test_copy_snapshot_error_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._root(tmp)
            txn = root / ".spell-sync.txn" / "tid"
            txn.mkdir(parents=True)
            with patch(
                "spell_sync.secure_artifacts.TrustedDirectory.copy_regular_file_from_path",
                side_effect=TrustedFsError("partial_write", "fail"),
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    copy_trusted_snapshot_file(
                        txn,
                        root=root,
                        base_name="dict",
                        source=wordlist,
                    )
                self.assertEqual(ctx.exception.code, "partial_write")

    def test_fsync_directory_without_o_directory_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with patch.object(os, "O_DIRECTORY", 0):
                with patch("spell_sync.secure_artifacts.os.open", return_value=3) as open_mock:
                    with patch("spell_sync.secure_artifacts._fsync_fd"):
                        with patch("spell_sync.secure_artifacts.os.close"):
                            _fsync_directory(path)
                            self.assertEqual(open_mock.call_args.args[0], path)
                            self.assertEqual(open_mock.call_args.args[1], os.O_RDONLY)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with patch.object(os, "O_DIRECTORY", 0o200000):
                with patch("spell_sync.secure_artifacts.os.open", return_value=3) as open_mock:
                    with patch("spell_sync.secure_artifacts._fsync_fd") as fsync_mock:
                        with patch("spell_sync.secure_artifacts.os.close") as close_mock:
                            _fsync_directory(path)
                            open_mock.assert_called_once()
                            fsync_mock.assert_called_once_with(3)
                            close_mock.assert_called_once_with(3)

    def test_fsync_directory_open_failure_non_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "spell_sync.secure_artifacts.os.open",
                side_effect=OSError(errno.EACCES, "denied"),
            ):
                with self.assertRaises(OSError):
                    _fsync_directory(Path(tmp))

    def test_relative_under_root_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, root = self._root(tmp)
            rel = _relative_under_root(root / "nested" / "file.txt", root)
            self.assertEqual(rel, Path("nested") / "file.txt")

    def test_reject_unsafe_component_file_and_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            dir_path = root / "dir"
            dir_path.mkdir()
            _reject_unsafe_component(file_path)
            _reject_unsafe_component(dir_path)

    def test_read_trusted_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, root = self._root(tmp)
            target = root / "data.txt"
            atomic_write_trusted_file(target, b"payload", root=root)
            self.assertEqual(read_trusted_regular_file(target, root=root), b"payload")


if __name__ == "__main__":
    unittest.main()
