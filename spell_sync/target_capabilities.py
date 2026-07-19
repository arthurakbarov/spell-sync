"""Stable target capability metadata (no runtime paths or filesystem access)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .project_setup.discovery import _CONFIG_TARGET_IDS, _DISPLAY_NAMES


class TargetFilterKind(str, Enum):
    FULL = "full"
    LATIN = "latin"
    CYRILLIC_AND_NON_LATIN = "cyrillic-and-non-latin"
    LOCALE_SPECIFIC = "locale-specific"


class TargetProfileModel(str, Enum):
    SINGLE = "single"
    MULTI_PROFILE = "multi-profile"
    SYSTEM_MANAGED = "system-managed"


class ApplicationClosePolicy(str, Enum):
    NOT_REQUIRED = "not-required"
    BLOCK_IF_RUNNING = "block-if-running"


_PLATFORM_ALL = frozenset({"macos", "windows", "linux"})
_PLATFORM_MACOS = frozenset({"macos"})
_PLATFORM_WINDOWS = frozenset({"windows"})


@dataclass(frozen=True)
class TargetCapability:
    identifier: str
    display_name: str
    platforms: frozenset[str]
    custom_dictionary_kind: str
    pull_supported: bool
    push_supported: bool
    filter_kind: TargetFilterKind
    profile_model: TargetProfileModel
    close_policy: ApplicationClosePolicy
    recovery_protected: bool


# Dictionary-level subset overrides (win-en, win-en-gb, win-ru under win_spelling).
DICTIONARY_FILTER_KINDS: dict[str, TargetFilterKind] = {
    "win-en": TargetFilterKind.LATIN,
    "win-en-gb": TargetFilterKind.LATIN,
    "win-ru": TargetFilterKind.CYRILLIC_AND_NON_LATIN,
}


def _capability(
    identifier: str,
    *,
    platforms: frozenset[str],
    custom_dictionary_kind: str,
    filter_kind: TargetFilterKind = TargetFilterKind.FULL,
    profile_model: TargetProfileModel = TargetProfileModel.MULTI_PROFILE,
    close_policy: ApplicationClosePolicy = ApplicationClosePolicy.NOT_REQUIRED,
) -> TargetCapability:
    return TargetCapability(
        identifier=identifier,
        display_name=_DISPLAY_NAMES.get(identifier, identifier),
        platforms=platforms,
        custom_dictionary_kind=custom_dictionary_kind,
        pull_supported=True,
        push_supported=True,
        filter_kind=filter_kind,
        profile_model=profile_model,
        close_policy=close_policy,
        recovery_protected=True,
    )


TARGET_CAPABILITIES: tuple[TargetCapability, ...] = tuple(
    sorted(
        (
            _capability("editors", platforms=_PLATFORM_ALL, custom_dictionary_kind="text"),
            _capability(
                "chrome",
                platforms=_PLATFORM_ALL,
                custom_dictionary_kind="chrome",
                close_policy=ApplicationClosePolicy.BLOCK_IF_RUNNING,
            ),
            _capability(
                "edge",
                platforms=_PLATFORM_ALL,
                custom_dictionary_kind="chrome",
                close_policy=ApplicationClosePolicy.BLOCK_IF_RUNNING,
            ),
            _capability("brave", platforms=_PLATFORM_ALL, custom_dictionary_kind="chrome"),
            _capability("vivaldi", platforms=_PLATFORM_ALL, custom_dictionary_kind="chrome"),
            _capability(
                "firefox",
                platforms=_PLATFORM_ALL,
                custom_dictionary_kind="text",
                close_policy=ApplicationClosePolicy.BLOCK_IF_RUNNING,
            ),
            _capability("neovim", platforms=_PLATFORM_ALL, custom_dictionary_kind="text"),
            _capability("jetbrains", platforms=_PLATFORM_ALL, custom_dictionary_kind="jetbrains"),
            _capability("hunspell", platforms=_PLATFORM_ALL, custom_dictionary_kind="hunspell"),
            _capability(
                "obsidian",
                platforms=_PLATFORM_ALL,
                custom_dictionary_kind="chrome",
                close_policy=ApplicationClosePolicy.BLOCK_IF_RUNNING,
            ),
            _capability("libreoffice", platforms=_PLATFORM_ALL, custom_dictionary_kind="text"),
            _capability(
                "macos_spelling",
                platforms=_PLATFORM_MACOS,
                custom_dictionary_kind="text",
                profile_model=TargetProfileModel.SYSTEM_MANAGED,
            ),
            _capability(
                "win_spelling",
                platforms=_PLATFORM_WINDOWS,
                custom_dictionary_kind="text",
                filter_kind=TargetFilterKind.LOCALE_SPECIFIC,
                profile_model=TargetProfileModel.SYSTEM_MANAGED,
            ),
        ),
        key=lambda item: item.identifier,
    )
)


def capability_by_id(identifier: str) -> TargetCapability | None:
    for capability in TARGET_CAPABILITIES:
        if capability.identifier == identifier:
            return capability
    return None


def all_capability_identifiers() -> frozenset[str]:
    return frozenset(item.identifier for item in TARGET_CAPABILITIES)


def config_target_identifiers() -> frozenset[str]:
    return frozenset(_CONFIG_TARGET_IDS)


def platform_capability_identifiers() -> frozenset[str]:
    return frozenset({"macos_spelling", "win_spelling"})


def registry_target_platform_pairs() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for capability in TARGET_CAPABILITIES:
        for platform in sorted(capability.platforms):
            pairs.append((capability.identifier, platform))
    return tuple(pairs)
