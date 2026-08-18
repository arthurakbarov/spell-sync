"""Read-only setup target discovery."""

from dataclasses import dataclass
from pathlib import Path

from ..dictionaries import Dictionary, discover_dictionaries
from ..paths import is_macos, is_windows
from ..read_outcome import ReadStatus, dictionary_read_result
from ..runtime_settings import RuntimeSettings
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
        "sublime",
        "jetbrains",
        "hunspell",
        "obsidian",
        "libreoffice",
        "macos_spelling",
        "win_spelling",
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
    enabled: bool = False
    # Per custom-dictionary file counts. Do not sum across files in a family:
    # two synced files would look like twice as many words.
    dictionary_word_counts: tuple[tuple[str, int], ...] = ()


def format_setup_target_word_meta(target: SetupTarget) -> str | None:
    """Meta line for Applications / setup family rows.

    Multi-dictionary families show a file count only; per-file counts are on child rows.
    """
    counts = target.dictionary_word_counts
    if not counts:
        if target.word_count is None:
            return None
        return f"{target.word_count:,} words"
    if len(counts) == 1:
        return f"{counts[0][1]:,} words"
    return f"{len(counts)} dictionaries"


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
    "sublime": "Sublime Text",
    "jetbrains": "JetBrains",
    "hunspell": "Hunspell",
    "obsidian": "Obsidian",
    "libreoffice": "LibreOffice",
    "macos_spelling": "macOS Spelling",
    "win_spelling": "Windows Spelling",
}

# Discovery dictionary names that map to a config family id.
_FAMILY_ALIASES = {
    "editor": "editors",
    "nvim": "neovim",
}


def dictionary_family_id(name: str) -> str:
    """Map a discovered dictionary name to its config / setup family id."""
    # Classic LocalDictionary is named "macos"; Sonoma+ AppleSpell uses "macos-*".
    if name == "macos" or name.startswith("macos-"):
        return "macos_spelling"
    if name.startswith("win-"):
        return "win_spelling"
    if name == "nvim" or name.startswith("nvim-"):
        return "neovim"
    if ":" in name:
        name = name.split(":", 1)[0]
    return _FAMILY_ALIASES.get(name, name)


def _family_id(dictionary: Dictionary) -> str:
    return dictionary_family_id(dictionary.name)


_PLATFORM_FAMILY_IDS = frozenset({"macos_spelling", "win_spelling"})


def _iter_target_groups(
    grouped: dict[str, list[Dictionary]],
) -> list[tuple[str, list[Dictionary]]]:
    groups: list[tuple[str, list[Dictionary]]] = []
    for target_id in sorted(grouped):
        items = grouped[target_id]
        if not items and target_id not in _PLATFORM_FAMILY_IDS:
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
    # Unreadable siblings (e.g. AppleSpell without Full Disk Access) must not
    # block a family that also has a readable path. Corrupt/unsupported do.
    blocking = {ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED}
    if statuses & blocking and ReadStatus.OK in statuses:
        return True
    return ReadStatus.CORRUPT in statuses and ReadStatus.UNREADABLE in statuses


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
    return identifier in _CONFIG_TARGET_IDS


def _default_discovery_config(enabled: tuple[str, ...]) -> dict[str, dict[str, object]]:
    enabled_set = set(enabled)
    flags: dict[str, object] = {
        name: (name in enabled_set if enabled else True) for name in _CONFIG_TARGET_IDS
    }
    return {"dictionaries": flags, "push": {}, "io": {"backup_keep": 3}}


def enabled_dictionary_targets(config: dict[str, dict[str, object]]) -> frozenset[str]:
    flags = config.get("dictionaries", {})
    enabled: set[str] = set()
    for target_id in _CONFIG_TARGET_IDS:
        value = flags.get(target_id)
        if value is True:
            enabled.add(target_id)
    return frozenset(enabled)


def discover_setup_targets(
    *,
    enabled_targets: frozenset[str] | None = None,
) -> SetupTargetDiscovery:
    # Always probe every configurable family so Setup / Applications can
    # show and re-enable currently disabled entries.
    config = _default_discovery_config(())
    # Probe every family without applying config excludes so Applications can
    # show excluded dictionaries as unchecked children.
    dictionaries = discover_dictionaries(
        RuntimeSettings.from_config_dict(config),
        apply_exclusions=False,
    )
    grouped: dict[str, list[Dictionary]] = {}
    for dictionary in dictionaries:
        grouped.setdefault(_family_id(dictionary), []).append(dictionary)

    if is_macos():
        grouped.setdefault("macos_spelling", [])
    if is_windows():
        grouped.setdefault("win_spelling", [])
    rows: list[SetupTarget] = []
    default_enabled: list[str] = []
    for target_id, items in _iter_target_groups(grouped):
        detected = bool(items)
        best_status = ReadStatus.MISSING
        word_count: int | None = None
        dictionary_word_counts: list[tuple[str, int]] = []
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
                count = len(result.words)
                dictionary_word_counts.append((dictionary.name, count))
                if dictionary.path:
                    sample_path = Path(dictionary.path)
                    sample_format = dictionary.format.value
            elif result.status is ReadStatus.MISSING:
                if best_status is ReadStatus.MISSING:
                    best_status = ReadStatus.MISSING
            elif result.status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
                if best_status not in (ReadStatus.OK, ReadStatus.EMPTY):
                    best_status = result.status
                    if result.detail:
                        detail = result.detail
            elif result.status is ReadStatus.UNREADABLE:
                if best_status not in (ReadStatus.OK, ReadStatus.EMPTY):
                    best_status = ReadStatus.UNREADABLE
                    detail = result.detail or "Unreadable dictionary"
            elif result.status is ReadStatus.EMPTY and best_status not in (
                ReadStatus.CORRUPT,
                ReadStatus.UNREADABLE,
                ReadStatus.UNSUPPORTED,
                ReadStatus.OK,
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
        # First-run: every found, readable, selectable family is on by default.
        enabled_by_default = selectable
        if enabled_by_default and target_id not in default_enabled:
            default_enabled.append(target_id)
        if not detected:
            detail = detail or "Not found"
        if best_status is ReadStatus.CORRUPT and not detail:
            detail = "Corrupt dictionary · cannot be enabled safely"
        if (
            target_id == "macos_spelling"
            and ReadStatus.OK in seen_statuses
            and ReadStatus.UNREADABLE in seen_statuses
            and detail is None
        ):
            detail = "AppleSpell path unreadable · classic LocalDictionary is usable"
        # Single readable dictionary keeps a scalar count; multi-file families
        # leave word_count unset so UI cannot accidentally show a summed total.
        if len(dictionary_word_counts) == 1:
            word_count = dictionary_word_counts[0][1]
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
                enabled=enabled_targets is not None and target_id in enabled_targets,
                dictionary_word_counts=tuple(dictionary_word_counts),
            )
        )
    return SetupTargetDiscovery(tuple(rows), tuple(default_enabled))


def config_draft_from_targets(
    selected_targets: tuple[str, ...],
    *,
    excluded_dictionaries: tuple[str, ...] = (),
) -> ProjectConfigDraft:
    for target in selected_targets:
        if target not in _CONFIG_TARGET_IDS:
            raise ValueError(f"Unknown setup target identifier: {target}")
    enabled = tuple(target for target in selected_targets if target in _CONFIG_TARGET_IDS)
    return ProjectConfigDraft(
        schema_version=1,
        enabled_targets=enabled,
        safety=SafetyConfig(),
        excluded_dictionaries=tuple(sorted(set(excluded_dictionaries))),
    )


def target_display_name(identifier: str) -> str:
    return _DISPLAY_NAMES.get(identifier, identifier)
