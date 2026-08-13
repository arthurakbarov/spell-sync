"""Optional-app hints before push."""

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
from .runtime_settings import RuntimeSettings
from .sublime_preferences import user_added_words_override_message


def optional_app_warn_messages(*, settings: RuntimeSettings | None = None) -> list[str]:
    """Guest-facing warn-level messages for optional apps (also used in JSON)."""
    runtime_settings = settings or RuntimeSettings.defaults()
    warnings: list[str] = []
    if enable_sublime(settings=runtime_settings):
        if not sublime_text_installed():
            warnings.append("Sublime Text not found — sublime dictionary will be created on push.")
        else:
            override = user_added_words_override_message()
            if override is not None:
                warnings.append(override)
    if enable_editors(settings=runtime_settings) and editor_uses_fallback():
        warnings.append(
            "No code editor install found — spell-sync-words.txt will use the default path."
        )
    return warnings


def warn_missing_optional_apps(*, settings: RuntimeSettings | None = None) -> None:
    """Call before push — does not block execution."""
    runtime_settings = settings or RuntimeSettings.defaults()
    for message in optional_app_warn_messages(settings=runtime_settings):
        log.warn(message)
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
