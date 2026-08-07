"""How to invoke the CLI from scripts and automation hints."""

from __future__ import annotations

import re
import shlex
import shutil
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_PYTHON_MINOR_DIR = re.compile(r"^(\d+)\.(\d+)$")


def _python_minor_key(name: str) -> tuple[int, int] | None:
    """Return (major, minor) for directory names like ``3.12``; else None."""
    match = _PYTHON_MINOR_DIR.fullmatch(name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def discover_pip_script() -> Path | None:
    """pip-installed spell-sync when the script directory is not on PATH.

    On macOS, user script dirs under ``~/Library/Python/<major.minor>/bin`` are
    considered in numeric version order (highest first). Non ``major.minor``
    directory names are ignored. Returns ``None`` when nothing is found.
    """
    if shutil.which("spell-sync"):
        return None
    candidates: list[Path] = []
    home = Path.home()
    if sys.platform == "darwin":
        python_lib = home / "Library" / "Python"
        if python_lib.is_dir():
            versioned: list[tuple[tuple[int, int], Path]] = []
            try:
                entries = list(python_lib.iterdir())
            except OSError:
                entries = []
            for entry in entries:
                if not entry.is_dir() or entry.is_symlink():
                    continue
                key = _python_minor_key(entry.name)
                if key is None:
                    continue
                script = entry / "bin" / "spell-sync"
                if script.is_file():
                    versioned.append((key, script))
            versioned.sort(key=lambda item: item[0], reverse=True)
            candidates.extend(script for _key, script in versioned)
    local = home / ".local" / "bin" / "spell-sync"
    if local.is_file():
        candidates.append(local)
    return candidates[0] if candidates else None


def path_export_for_script(script: Path) -> str:
    """Shell export line to put a pip script directory on PATH (POSIX-quoted)."""
    bindir = shlex.quote(script.parent.as_posix())
    return f"export PATH={bindir}:$PATH"


def cli_argv() -> list[str]:
    """Command argv prefix: spell-sync (pip) or python -m spell_sync (clone)."""
    exe = shutil.which("spell-sync")
    if exe:
        return [exe]
    return [sys.executable, "-m", "spell_sync"]


def cli_shell_prefix() -> str:
    """Shell-safe CLI prefix (no subcommand)."""
    return " ".join(shlex.quote(part) for part in cli_argv())


def cli_shell_command(subcommand: str) -> str:
    """Single shell command string for cron/launchd examples."""
    return f"{cli_shell_prefix()} {shlex.quote(subcommand)}"


def read_pyproject_version(pyproject: Path) -> str | None:
    """Return ``project.version`` from a ``pyproject.toml``, or ``None`` if missing/unreadable."""
    try:
        raw = pyproject.read_bytes()
    except OSError:
        return None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    value = project.get("version")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


_UNKNOWN_PACKAGE_VERSION = "0+unknown"


def installed_package_version() -> str:
    """Installed package version, pyproject.toml in a checkout, or a safe unknown marker."""
    try:
        return version("spell-sync")
    except PackageNotFoundError:
        pass
    source_root = Path(__file__).resolve().parent.parent
    from_pyproject = read_pyproject_version(source_root / "pyproject.toml")
    if from_pyproject:
        return from_pyproject
    return _UNKNOWN_PACKAGE_VERSION
