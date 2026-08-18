"""Regenerate Neovim .spl spell file after push."""

import shutil
import subprocess
from pathlib import Path

from .config import neovim_mkspell_after_push
from .log import log
from .runtime_settings import RuntimeSettings
from .subprocess_utils import trim_subprocess_text


def _vim_single_quote(text: str) -> str:
    """Vimscript single-quoted string literal."""
    return "'" + text.replace("'", "''") + "'"


def _mkspell_ex_command(add_path: Path, spl_path: Path) -> str:
    add = _vim_single_quote(str(add_path))
    spl = _vim_single_quote(str(spl_path))
    return f"silent! execute 'mkspell! ' . fnameescape({add}) . ' ' . fnameescape({spl})"


def run_mkspell_for_add_file(add_path: Path) -> bool:
    """Run nvim --headless mkspell on add_path. Returns True if .spl was regenerated."""
    nvim = shutil.which("nvim")
    if nvim is None:
        log.detail("mkspell skipped: nvim not on PATH")
        return False
    if not add_path.is_file():
        log.detail(f"mkspell skipped: {add_path.name} missing")
        return False

    spl_path = add_path.with_suffix(".spl")
    cmd = [
        nvim,
        "--headless",
        "-c",
        _mkspell_ex_command(add_path, spl_path),
        "-c",
        "qa!",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except OSError, subprocess.TimeoutExpired:
        log.warn(f"mkspell failed for {add_path.name}")
        return False
    if result.returncode != 0:
        detail = trim_subprocess_text(result.stderr or "")
        if not detail:
            detail = trim_subprocess_text(result.stdout or "")
        suffix = f": {detail}" if detail else ""
        log.warn(f"mkspell failed for {add_path.name} (exit {result.returncode}){suffix}")
        return False
    if not spl_path.is_file():
        log.warn(f"mkspell did not create {spl_path.name}")
        return False
    log.detail(f"mkspell regenerated {spl_path.name}")
    return True


def mkspell_after_neovim_writes(
    written_names: tuple[str, ...],
    *,
    settings: RuntimeSettings,
) -> None:
    """Run mkspell for each written Neovim dictionary when configured."""
    if not neovim_mkspell_after_push(settings=settings):
        return
    from .paths import neovim_dict_paths

    paths = dict(neovim_dict_paths())
    for name in written_names:
        if name != "nvim" and not name.startswith("nvim-"):
            continue
        path = paths.get(name) or paths.get("nvim")
        if path is not None:
            run_mkspell_for_add_file(path)
