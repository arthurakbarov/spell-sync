"""Tests for package member privacy rules."""

from __future__ import annotations

import io
import sys
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


def test_scan_archive_roundtrip(tmp_path: Path) -> None:
    archive = tmp_path / "sample.whl"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("spell_sync/cli.py", "x\n")
        zf.writestr("tests/secret.py", "y\n")
    archive.write_bytes(buf.getvalue())
    errors = scan_archive(archive)
    assert any("tests/" in err for err in errors)
