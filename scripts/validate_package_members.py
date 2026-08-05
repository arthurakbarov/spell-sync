#!/usr/bin/env python3
"""Forbidden member rules for wheels/sdists (stdlib; inspect namelists)."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PREFIXES = (
    "tests/",
    ".artifacts/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".venv/",
    "htmlcov/",
)
FORBIDDEN_BASENAMES = frozenset(
    {
        "wordlist.txt",
        "spell-sync.toml",
        "lint-whitelist.txt",
        "operation-history.jsonl",
        "operation-history.lock",
    }
)
ALLOWED_BASENAME_EXCEPTIONS = frozenset(
    {
        "spell_sync/bundled/lint-whitelist.txt",
        "spell_sync/bundled/spell-sync.toml.example",
        "spell_sync/bundled/wordlist.txt.example",
    }
)


def package_member_violations(names: list[str]) -> list[str]:
    """Return human-readable violations for archive member paths."""
    errors: list[str] = []
    for raw in names:
        name = raw.replace("\\", "/").lstrip("./")
        if name in ALLOWED_BASENAME_EXCEPTIONS:
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if name.startswith(prefix):
                errors.append(f"forbidden-prefix:{name}")
                break
        base = name.rsplit("/", 1)[-1]
        if base in FORBIDDEN_BASENAMES and name not in ALLOWED_BASENAME_EXCEPTIONS:
            errors.append(f"forbidden-basename:{name}")
    return errors


def scan_archive(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return package_member_violations(archive.namelist())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archives",
        nargs="*",
        type=Path,
        help="Wheel/sdist/zip paths (default: dist/*.whl and dist/*.tar.gz if present)",
    )
    args = parser.parse_args(argv)
    archives = list(args.archives)
    if not archives:
        dist = ROOT / "dist"
        if dist.is_dir():
            archives.extend(sorted(dist.glob("*.whl")))
            archives.extend(sorted(dist.glob("*.tar.gz")))
    if not archives:
        print("PACKAGE_MEMBERS_RESULT=skipped")
        print("PACKAGE_MEMBERS_REASON=no-archives")
        return 0
    failed = 0
    for archive in archives:
        if not archive.is_file():
            print(f"PACKAGE_MEMBERS_MISSING={archive.as_posix()}")
            failed += 1
            continue
        errors = scan_archive(archive)
        if errors:
            failed += 1
            print(f"PACKAGE_MEMBERS_ARCHIVE={archive.name}")
            for err in errors:
                print(f"PACKAGE_MEMBERS_ERROR={err}")
    if failed:
        print("PACKAGE_MEMBERS_RESULT=failed")
        return 1
    print("PACKAGE_MEMBERS_RESULT=success")
    print(f"PACKAGE_MEMBERS_ARCHIVES={len(archives)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
