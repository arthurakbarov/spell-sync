"""Tests for package member privacy rules."""

from __future__ import annotations

import io
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_package_members import (  # noqa: E402
    package_member_violations,
    scan_archive,
)


def test_clean_wheel_members_pass() -> None:
    names = [
        "spell_sync/__init__.py",
        "spell_sync/bundled/lint-whitelist.txt",
        "spell_sync/bundled/wordlist.txt.example",
        "spell_sync-0.3.0.dist-info/METADATA",
    ]
    assert package_member_violations(names) == []


def test_forbidden_tests_prefix_detected() -> None:
    errors = package_member_violations(["tests/test_foo.py", "spell_sync/cli.py"])
    assert any(err.startswith("forbidden-prefix:tests/") for err in errors)


def test_forbidden_personal_basename_detected() -> None:
    errors = package_member_violations(["wordlist.txt", "spell_sync/cli.py"])
    assert any("forbidden-basename:wordlist.txt" in err for err in errors)


def test_sdist_nested_prefix_stripped_for_rules() -> None:
    """sdists nest under spell_sync-VERSION/; rules must still see tests/."""
    errors = package_member_violations(
        [
            "spell_sync-0.3.0/spell_sync/cli.py",
            "spell_sync-0.3.0/tests/test_foo.py",
            "spell_sync-0.3.0/spell_sync/bundled/lint-whitelist.txt",
        ]
    )
    assert any("forbidden-prefix:tests/" in err for err in errors)
    assert not any("lint-whitelist" in err for err in errors)


def test_scan_archive_roundtrip(tmp_path: Path) -> None:
    archive = tmp_path / "sample.whl"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("spell_sync/cli.py", "x\n")
        zf.writestr("tests/secret.py", "y\n")
    archive.write_bytes(buf.getvalue())
    errors = scan_archive(archive)
    assert any("tests/" in err for err in errors)


def test_scan_sdist_tar_gz(tmp_path: Path) -> None:
    archive = tmp_path / "spell_sync-0.3.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name="spell_sync-0.3.0/spell_sync/cli.py")
        payload = b"x\n"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
        bad = tarfile.TarInfo(name="spell_sync-0.3.0/tests/leak.py")
        bad_payload = b"y\n"
        bad.size = len(bad_payload)
        tf.addfile(bad, io.BytesIO(bad_payload))
    errors = scan_archive(archive)
    assert any("tests/" in err for err in errors)


def test_scan_rejects_unreadable_archive(tmp_path: Path) -> None:
    bogus = tmp_path / "not-an-archive.tar.gz"
    bogus.write_text("not a tar", encoding="utf-8")
    try:
        scan_archive(bogus)
    except Exception:
        return
    raise AssertionError("expected scan_archive to reject a non-tar payload")


def test_manifest_prunes_tests_from_sdist() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "prune tests" in manifest
