"""Optional-app hints before push."""

from __future__ import annotations

from .config import (
    enable_brave,
    enable_chrome,
    enable_edge,
    enable_editors,
    enable_firefox,
    enable_hunspell,
    enable_jetbrains,
    enable_obsidian,
    enable_vivaldi,
)
from .log import log
from .paths import (
    brave_dict_paths,
    chrome_dict_paths,
    edge_dict_paths,
    editor_uses_fallback,
    firefox_dict_paths,
    hunspell_dict_paths,
    jetbrains_dict_paths,
    obsidian_dict_paths,
    sublime_text_installed,
    vivaldi_dict_paths,
)


def warn_missing_optional_apps() -> None:
    """Call before push — does not block execution."""
    if not sublime_text_installed():
        log.warn("Sublime Text not found — sublime dictionary will be created on push.")
    if enable_editors() and editor_uses_fallback():
        log.warn("No code editor install found — spell-sync-words.txt will use the default path.")
    if enable_chrome() and not chrome_dict_paths():
        log.detail("Google Chrome not found. Chrome dictionaries skipped.")
    if enable_edge() and not edge_dict_paths():
        log.detail("Microsoft Edge not found. Edge dictionaries skipped.")
    if enable_brave() and not brave_dict_paths():
        log.detail("Brave not found. Brave dictionaries skipped.")
    if enable_vivaldi() and not vivaldi_dict_paths():
        log.detail("Vivaldi not found. Vivaldi dictionaries skipped.")
    if enable_firefox() and not firefox_dict_paths():
        log.detail("Firefox not found. Firefox dictionaries skipped.")
    if enable_jetbrains() and not jetbrains_dict_paths():
        log.detail("JetBrains IDE not found. JetBrains dictionaries skipped.")
    if enable_hunspell() and not hunspell_dict_paths():
        log.detail("Hunspell personal dictionary not found. Hunspell dictionaries skipped.")
    if enable_obsidian() and not obsidian_dict_paths():
        log.detail("Obsidian not found. Obsidian dictionary skipped.")
