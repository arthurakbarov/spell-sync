"""Optional-app and workspace honesty warnings for plan, status, doctor, and Update."""

from dataclasses import dataclass
from pathlib import Path

from .config import (
    enable_brave,
    enable_chrome,
    enable_edge,
    enable_editors,
    enable_firefox,
    enable_hunspell,
    enable_jetbrains,
    enable_obsidian,
    enable_sublime,
    enable_vivaldi,
)
from .guest_messages import CLEANUP_PENDING_WARN
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
from .push_journal import JournalLoadStatus, load_journal_result
from .runtime_settings import RuntimeSettings
from .sublime_preferences import user_added_words_override_message
from .workspace_git import inspect_workspace_git, workspace_git_dirty_message

SUBLIME_NOT_FOUND = "sublime_not_found"
SUBLIME_USER_OVERRIDE = "sublime_user_override"
EDITOR_FALLBACK = "editor_fallback"


@dataclass(frozen=True, slots=True)
class OptionalAppWarning:
    """Coded optional-app honesty hint (message stays guest-facing)."""

    code: str
    message: str


def optional_app_warn_hints(*, settings: RuntimeSettings | None = None) -> list[OptionalAppWarning]:
    """Structured warn-level hints for optional apps."""
    runtime_settings = settings or RuntimeSettings.defaults()
    warnings: list[OptionalAppWarning] = []
    if enable_sublime(settings=runtime_settings):
        if not sublime_text_installed():
            warnings.append(
                OptionalAppWarning(
                    SUBLIME_NOT_FOUND,
                    "Sublime Text not found — Update my apps will create the Sublime dictionary.",
                )
            )
        else:
            override = user_added_words_override_message()
            if override is not None:
                warnings.append(OptionalAppWarning(SUBLIME_USER_OVERRIDE, override))
    if enable_editors(settings=runtime_settings) and editor_uses_fallback():
        warnings.append(
            OptionalAppWarning(
                EDITOR_FALLBACK,
                "No code editor install found — spell-sync-words.txt will use the default path.",
            )
        )
    return warnings


def optional_app_warn_messages(*, settings: RuntimeSettings | None = None) -> list[str]:
    """Guest-facing warn-level messages for optional apps (also used in JSON)."""
    return [hint.message for hint in optional_app_warn_hints(settings=settings)]


def project_honesty_warnings(
    wordlist: Path,
    *,
    settings: RuntimeSettings | None = None,
) -> list[str]:
    """Optional-app and dirty-workspace warnings shared by CLI, TUI, and JSON."""
    warnings = optional_app_warn_messages(settings=settings)
    journal_wordlist = wordlist / "wordlist.txt" if wordlist.is_dir() else wordlist
    if load_journal_result(journal_wordlist).status is JournalLoadStatus.VALID_COMPLETED:
        warnings.append(CLEANUP_PENDING_WARN)
    root = wordlist if wordlist.is_dir() else wordlist.parent
    git_status = inspect_workspace_git(root)
    if git_status is not None and git_status.is_dirty:
        warnings.append(workspace_git_dirty_message(git_status))
    return warnings


def log_skipped_optional_app_details(*, settings: RuntimeSettings | None = None) -> None:
    """Detail-only: enabled apps with no install are skipped (does not block)."""
    runtime_settings = settings or RuntimeSettings.defaults()
    if enable_chrome(settings=runtime_settings) and not chrome_dict_paths():
        log.detail("Google Chrome not found. Chrome dictionaries skipped.")
    if enable_edge(settings=runtime_settings) and not edge_dict_paths():
        log.detail("Microsoft Edge not found. Edge dictionaries skipped.")
    if enable_brave(settings=runtime_settings) and not brave_dict_paths():
        log.detail("Brave not found. Brave dictionaries skipped.")
    if enable_vivaldi(settings=runtime_settings) and not vivaldi_dict_paths():
        log.detail("Vivaldi not found. Vivaldi dictionaries skipped.")
    if enable_firefox(settings=runtime_settings) and not firefox_dict_paths():
        log.detail("Firefox not found. Firefox dictionaries skipped.")
    if enable_jetbrains(settings=runtime_settings) and not jetbrains_dict_paths():
        log.detail("JetBrains IDE not found. JetBrains dictionaries skipped.")
    if enable_hunspell(settings=runtime_settings) and not hunspell_dict_paths():
        log.detail("Hunspell personal dictionary not found. Hunspell dictionaries skipped.")
    if enable_obsidian(settings=runtime_settings) and not obsidian_dict_paths():
        log.detail("Obsidian not found. Obsidian dictionary skipped.")
