"""Read-only setup target discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ..dictionaries import Dictionary, discover_dictionaries
from ..paths import is_macos
from ..read_outcome import ReadStatus, dictionary_read_result
from .draft import ProjectConfigDraft, SafetyConfig


@dataclass(frozen=True)
class SetupTargetRow:
    target_id: str
    display_name: str
    path: str
    format: str
    detected: bool
    available: bool
    read_status: str
    word_count: int | None
    warning: str | None
    can_enable: bool


@dataclass(frozen=True)
class SetupTargetDiscovery:
    targets: tuple[SetupTargetRow, ...]
    default_enabled: tuple[str, ...]


_DISPLAY_NAMES = {
    "editors": "Editor dictionaries",
    "chrome": "Chrome",
    "edge": "Edge",
    "brave": "Brave",
    "vivaldi": "Vivaldi",
    "firefox": "Firefox",
    "neovim": "Neovim",
    "jetbrains": "JetBrains",
    "hunspell": "Hunspell",
    "obsidian": "Obsidian",
    "libreoffice": "LibreOffice",
    "macos_spelling": "macOS Spelling",
    "win_spelling": "Windows Spelling",
    "sublime": "Sublime Text",
}


def _family_id(dictionary: Dictionary) -> str:
    if dictionary.name.startswith("macos-"):
        return "macos_spelling"
    if dictionary.name.startswith("win-"):
        return "win_spelling"
    if ":" in dictionary.name:
        return dictionary.name.split(":", 1)[0]
    return dictionary.name


def _iter_target_groups(
    grouped: dict[str, list[Dictionary]],
) -> list[tuple[str, list[Dictionary]]]:
    groups: list[tuple[str, list[Dictionary]]] = []
    for target_id in sorted(grouped):
        items = grouped[target_id]
        if not items and target_id not in {"macos_spelling"}:
            continue
        groups.append((target_id, items))
    return groups


def _default_discovery_config(enabled: tuple[str, ...]) -> dict[str, dict[str, object]]:
    enabled_set = set(enabled)
    flags: dict[str, object] = {
        name: (name in enabled_set if enabled else True)
        for name in (
            "editors",
            "chrome",
            "edge",
            "brave",
            "vivaldi",
            "firefox",
            "neovim",
            "jetbrains",
            "hunspell",
            "obsidian",
            "libreoffice",
        )
    }
    return {"dictionaries": flags, "push": {}, "io": {"backup_keep": 3}}


def discover_setup_targets(
    *,
    selected_targets: tuple[str, ...] | None = None,
) -> SetupTargetDiscovery:
    config = _default_discovery_config(selected_targets or ())
    dictionaries = discover_dictionaries(config)
    grouped: dict[str, list[Dictionary]] = {}
    for dictionary in dictionaries:
        grouped.setdefault(_family_id(dictionary), []).append(dictionary)

    if is_macos():
        grouped.setdefault("macos_spelling", [])
    rows: list[SetupTargetRow] = []
    default_enabled: list[str] = []
    for target_id, items in _iter_target_groups(grouped):
        detected = bool(items)
        best_status = ReadStatus.MISSING
        word_count: int | None = None
        warning: str | None = None
        available = False
        sample_path = ""
        sample_format = "text"
        for dictionary in items:
            result = dictionary_read_result(dictionary)
            sample_path = sample_path or dictionary.path
            sample_format = dictionary.format.value
            if result.status is ReadStatus.OK:
                available = True
                best_status = ReadStatus.OK
                word_count = (word_count or 0) + len(result.words)
            elif result.status is ReadStatus.MISSING:
                if best_status is ReadStatus.MISSING:
                    best_status = ReadStatus.MISSING
            elif result.status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
                best_status = result.status
                warning = result.detail or result.status.value
            elif result.status is ReadStatus.UNREADABLE:
                best_status = ReadStatus.UNREADABLE
                warning = result.detail or "Unreadable dictionary"
            elif result.status is ReadStatus.EMPTY and best_status not in (
                ReadStatus.CORRUPT,
                ReadStatus.UNREADABLE,
                ReadStatus.UNSUPPORTED,
            ):
                best_status = ReadStatus.EMPTY
                available = True
        can_enable = available and best_status not in (
            ReadStatus.CORRUPT,
            ReadStatus.UNREADABLE,
            ReadStatus.UNSUPPORTED,
        )
        if can_enable and target_id not in default_enabled:
            default_enabled.append(target_id)
        if not detected:
            warning = warning or "Not found"
        rows.append(
            SetupTargetRow(
                target_id=target_id,
                display_name=_DISPLAY_NAMES.get(target_id, target_id),
                path=sample_path or "Not found",
                format=sample_format,
                detected=detected,
                available=available,
                read_status=best_status.value,
                word_count=word_count,
                warning=warning,
                can_enable=can_enable,
            )
        )
    return SetupTargetDiscovery(tuple(rows), tuple(default_enabled))


def config_draft_from_targets(selected_targets: tuple[str, ...]) -> ProjectConfigDraft:
    enabled = tuple(
        target
        for target in selected_targets
        if target
        not in {
            "macos_spelling",
            "win_spelling",
            "sublime",
        }
    )
    return ProjectConfigDraft(
        schema_version=1,
        enabled_targets=enabled,
        safety=SafetyConfig(),
    )
