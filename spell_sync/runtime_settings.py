"""Typed immutable runtime settings parsed from spell-sync.toml."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PUSH_GUARD_WORDLIST_MAX = 10
PUSH_GUARD_LOCAL_MIN = 20
PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT = 50
BACKUP_KEEP_DEFAULT = 3


@dataclass(frozen=True, slots=True)
class DictionarySettings:
    editors: bool = True
    chrome: bool = True
    edge: bool = True
    brave: bool = True
    vivaldi: bool = True
    firefox: bool = True
    neovim: bool = True
    sublime: bool = True
    jetbrains: bool = True
    hunspell: bool = True
    obsidian: bool = True
    libreoffice: bool = True
    macos_spelling: bool = True
    win_spelling: bool = True
    # Exact discovery names (e.g. editor:vscode) skipped while the family stays on.
    excluded: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PushPolicy:
    guard_wordlist_max: int = PUSH_GUARD_WORDLIST_MAX
    guard_local_min: int = PUSH_GUARD_LOCAL_MIN
    strict: bool = False
    max_removals_without_confirm: int = PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT


@dataclass(frozen=True, slots=True)
class IoPolicy:
    backup_keep: int = BACKUP_KEEP_DEFAULT


@dataclass(frozen=True, slots=True)
class NeovimPolicy:
    mkspell_after_push: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    dictionaries: DictionarySettings
    push: PushPolicy
    io: IoPolicy
    neovim: NeovimPolicy

    @classmethod
    def defaults(cls) -> RuntimeSettings:
        return cls.from_config_dict({})

    @classmethod
    def from_config_dict(cls, config: Mapping[str, Mapping[str, Any]]) -> RuntimeSettings:
        dictionaries = config.get("dictionaries", {})
        push = config.get("push", {})
        io_section = config.get("io", {})
        neovim = config.get("neovim", {})

        return cls(
            dictionaries=DictionarySettings(
                editors=_bool(dictionaries, "editors", True),
                chrome=_bool(dictionaries, "chrome", True),
                edge=_bool(dictionaries, "edge", True),
                brave=_bool(dictionaries, "brave", True),
                vivaldi=_bool(dictionaries, "vivaldi", True),
                firefox=_bool(dictionaries, "firefox", True),
                neovim=_bool(dictionaries, "neovim", True),
                sublime=_bool(dictionaries, "sublime", True),
                jetbrains=_bool(dictionaries, "jetbrains", True),
                hunspell=_bool(dictionaries, "hunspell", True),
                obsidian=_bool(dictionaries, "obsidian", True),
                libreoffice=_bool(dictionaries, "libreoffice", True),
                macos_spelling=_bool(dictionaries, "macos_spelling", True),
                win_spelling=_bool(dictionaries, "win_spelling", True),
                excluded=_string_set(dictionaries, "excluded"),
            ),
            push=PushPolicy(
                guard_wordlist_max=_int(push, "guard_wordlist_max", PUSH_GUARD_WORDLIST_MAX),
                guard_local_min=_int(push, "guard_local_min", PUSH_GUARD_LOCAL_MIN),
                strict=_bool(push, "strict", False),
                max_removals_without_confirm=_int(
                    push,
                    "max_removals_without_confirm",
                    PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT,
                ),
            ),
            io=IoPolicy(
                backup_keep=max(0, _int(io_section, "backup_keep", BACKUP_KEEP_DEFAULT)),
            ),
            neovim=NeovimPolicy(
                mkspell_after_push=_bool(neovim, "mkspell_after_push", False),
            ),
        )

    def enabled_dictionary_target_ids(self) -> frozenset[str]:
        mapping = {
            "editors": self.dictionaries.editors,
            "chrome": self.dictionaries.chrome,
            "edge": self.dictionaries.edge,
            "brave": self.dictionaries.brave,
            "vivaldi": self.dictionaries.vivaldi,
            "firefox": self.dictionaries.firefox,
            "neovim": self.dictionaries.neovim,
            "sublime": self.dictionaries.sublime,
            "jetbrains": self.dictionaries.jetbrains,
            "hunspell": self.dictionaries.hunspell,
            "obsidian": self.dictionaries.obsidian,
            "libreoffice": self.dictionaries.libreoffice,
            "macos_spelling": self.dictionaries.macos_spelling,
            "win_spelling": self.dictionaries.win_spelling,
        }
        return frozenset(name for name, enabled in mapping.items() if enabled)


def _bool(section: Mapping[str, Any], key: str, default: bool) -> bool:
    value = section.get(key)
    if isinstance(value, bool):
        return value
    return default


def _string_set(section: Mapping[str, Any], key: str) -> frozenset[str]:
    value = section.get(key)
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str) and item)


def _int(section: Mapping[str, Any], key: str, default: int) -> int:
    value = section.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
