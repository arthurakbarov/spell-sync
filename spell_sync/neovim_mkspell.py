"""Regenerate Neovim .spl spell file after push."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .log import log
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
        log.detail(f"mkspell skipped: {add_path} missing")
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
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warn(f"mkspell failed for {add_path.name}: {exc}")
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


def mkspell_after_neovim_writes(written_names: tuple[str, ...]) -> None:
    """Run mkspell for each written Neovim dictionary when configured."""
    from .config import neovim_mkspell_after_push

    if not neovim_mkspell_after_push():
        return
    for name in written_names:
        if not name.startswith("nvim-"):
            continue
        from .paths import neovim_dict_paths

        for dict_name, path in neovim_dict_paths():
            if dict_name == name:
                run_mkspell_for_add_file(path)
                break
