"""Read-only setup target discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..dictionaries import Dictionary, discover_dictionaries
from ..paths import is_macos, is_windows
from ..read_outcome import ReadStatus, dictionary_read_result
from .draft import ProjectConfigDraft, SafetyConfig

_CONFIG_TARGET_IDS = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class SetupTarget:
    identifier: str
    display_name: str
    path: Path | None
    format_name: str
    detected: bool
    available: bool
    readable: bool
    supported: bool
    enabled_by_default: bool
    selectable: bool
    word_count: int | None
    status: str
    detail: str | None


@dataclass(frozen=True)
class SetupTargetDiscovery:
    targets: tuple[SetupTarget, ...]
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


def _platform_supported(identifier: str) -> bool:
    if identifier == "macos_spelling":
        return is_macos()
    if identifier == "win_spelling":
        return is_windows()
    return True


def _ambiguous_discovery(items: list[Dictionary], statuses: set[ReadStatus]) -> bool:
    if len(items) <= 1:
        return False
    blocking = {ReadStatus.CORRUPT, ReadStatus.UNREADABLE, ReadStatus.UNSUPPORTED}
    if statuses & blocking and ReadStatus.OK in statuses:
        return True
    if ReadStatus.CORRUPT in statuses and ReadStatus.UNREADABLE in statuses:
        return True
    return False


def _target_selectable(
    *,
    identifier: str,
    detected: bool,
    available: bool,
    readable: bool,
    supported: bool,
    status: ReadStatus,
    ambiguous: bool,
) -> bool:
    if not supported or ambiguous:
        return False
    if status in (ReadStatus.CORRUPT, ReadStatus.UNREADABLE, ReadStatus.UNSUPPORTED):
        return False
    if not detected:
        return False
    if not available or not readable:
        return False
    if identifier not in _CONFIG_TARGET_IDS and identifier not in {
        "macos_spelling",
        "win_spelling",
    }:
        return False
    return True


def _default_discovery_config(enabled: tuple[str, ...]) -> dict[str, dict[str, object]]:
    enabled_set = set(enabled)
    flags: dict[str, object] = {
        name: (name in enabled_set if enabled else True) for name in _CONFIG_TARGET_IDS
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
    rows: list[SetupTarget] = []
    default_enabled: list[str] = []
    for target_id, items in _iter_target_groups(grouped):
        detected = bool(items)
        best_status = ReadStatus.MISSING
        word_count: int | None = None
        detail: str | None = None
        available = False
        sample_path: Path | None = None
        sample_format = "text"
        seen_statuses: set[ReadStatus] = set()
        for dictionary in items:
            result = dictionary_read_result(dictionary)
            seen_statuses.add(result.status)
            if sample_path is None and dictionary.path:
                sample_path = Path(dictionary.path)
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
                if result.detail:
                    detail = result.detail
            elif result.status is ReadStatus.UNREADABLE:
                best_status = ReadStatus.UNREADABLE
                detail = result.detail or "Unreadable dictionary"
            elif result.status is ReadStatus.EMPTY and best_status not in (
                ReadStatus.CORRUPT,
                ReadStatus.UNREADABLE,
                ReadStatus.UNSUPPORTED,
            ):
                best_status = ReadStatus.EMPTY
                available = True
        readable = best_status in (ReadStatus.OK, ReadStatus.EMPTY)
        supported = _platform_supported(target_id)
        ambiguous = _ambiguous_discovery(items, seen_statuses)
        selectable = _target_selectable(
            identifier=target_id,
            detected=detected,
            available=available,
            readable=readable,
            supported=supported,
            status=best_status,
            ambiguous=ambiguous,
        )
        enabled_by_default = selectable and detected and available and readable and supported
        if enabled_by_default and target_id not in default_enabled:
            default_enabled.append(target_id)
        if not detected:
            detail = detail or "Not found"
        if best_status is ReadStatus.CORRUPT and not detail:
            detail = "Corrupt dictionary · cannot be enabled safely"
        rows.append(
            SetupTarget(
                identifier=target_id,
                display_name=_DISPLAY_NAMES.get(target_id, target_id),
                path=sample_path,
                format_name=sample_format,
                detected=detected,
                available=available,
                readable=readable,
                supported=supported,
                enabled_by_default=enabled_by_default,
                selectable=selectable,
                word_count=word_count,
                status=best_status.value,
                detail=detail,
            )
        )
    return SetupTargetDiscovery(tuple(rows), tuple(default_enabled))


def config_draft_from_targets(selected_targets: tuple[str, ...]) -> ProjectConfigDraft:
    allowed = _CONFIG_TARGET_IDS | {"macos_spelling", "win_spelling"}
    for target in selected_targets:
        if target not in allowed:
            raise ValueError(f"Unknown setup target identifier: {target}")
    enabled = tuple(target for target in selected_targets if target in _CONFIG_TARGET_IDS)
    return ProjectConfigDraft(
        schema_version=1,
        enabled_targets=enabled,
        safety=SafetyConfig(),
    )


def target_display_name(identifier: str) -> str:
    return _DISPLAY_NAMES.get(identifier, identifier)
