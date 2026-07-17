"""How to invoke the CLI from scripts and automation hints."""

from __future__ import annotations

import shlex
import shutil
import sys
from importlib.metadata import version
from pathlib import Path


def discover_pip_script() -> Path | None:
    """pip-installed spell-sync when the script directory is not on PATH."""
    if shutil.which("spell-sync"):
        return None
    candidates: list[Path] = []
    home = Path.home()
    if sys.platform == "darwin":
        python_lib = home / "Library" / "Python"
        if python_lib.is_dir():
            for entry in sorted(python_lib.iterdir(), reverse=True):
                script = entry / "bin" / "spell-sync"
                if script.is_file():
                    candidates.append(script)
    local = home / ".local" / "bin" / "spell-sync"
    if local.is_file():
        candidates.append(local)
    return candidates[0] if candidates else None


def path_export_for_script(script: Path) -> str:
    """Shell export line to put a pip script directory on PATH."""
    bindir = script.parent.as_posix()
    return f'export PATH="{bindir}:$PATH"'


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
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version = "):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def installed_package_version() -> str:
    """Installed package version, or pyproject.toml when running from a checkout."""
    try:
        return version("spell-sync")
    except Exception:
        pass
    source_root = Path(__file__).resolve().parent.parent
    from_pyproject = read_pyproject_version(source_root / "pyproject.toml")
    if from_pyproject:
        return from_pyproject
    return version("spell-sync")
