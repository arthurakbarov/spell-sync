"""Example files shipped inside the installed package."""

from __future__ import annotations

import shutil
from pathlib import Path

_BUNDLED_DIR = Path(__file__).resolve().parent / "bundled"

_INIT_FILES = (
    ("wordlist.txt.example", "wordlist.txt"),
    ("spell-sync.toml.example", "spell-sync.toml"),
    ("lint-whitelist.txt", "lint-whitelist.txt"),
)


def bundled_path(name: str) -> Path:
    return _BUNDLED_DIR / name


def init_project_directory(target: Path | None = None) -> list[str]:
    """Copy bundled examples into target directory. Returns created filenames."""
    root = target or Path.cwd()
    created: list[str] = []
    for source_name, dest_name in _INIT_FILES:
        source = bundled_path(source_name)
        dest = root / dest_name
        if dest.exists():
            continue
        shutil.copyfile(source, dest)
        created.append(dest_name)
    return created
