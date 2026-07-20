"""Typed immutable runtime settings parsed from spell-sync.toml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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
    jetbrains: bool = True
    hunspell: bool = True
    obsidian: bool = True
    libreoffice: bool = True


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
                jetbrains=_bool(dictionaries, "jetbrains", True),
                hunspell=_bool(dictionaries, "hunspell", True),
                obsidian=_bool(dictionaries, "obsidian", True),
                libreoffice=_bool(dictionaries, "libreoffice", True),
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
            "jetbrains": self.dictionaries.jetbrains,
            "hunspell": self.dictionaries.hunspell,
            "obsidian": self.dictionaries.obsidian,
            "libreoffice": self.dictionaries.libreoffice,
        }
        return frozenset(name for name, enabled in mapping.items() if enabled)


def _bool(section: Mapping[str, Any], key: str, default: bool) -> bool:
    value = section.get(key)
    if isinstance(value, bool):
        return value
    return default


def _int(section: Mapping[str, Any], key: str, default: int) -> int:
    value = section.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
