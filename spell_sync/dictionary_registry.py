"""Optional dictionary discovery sources (config-gated adapters)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dictionaries import Dictionary


@dataclass(frozen=True)
class DictionarySource:
    """One configurable dictionary family discovered at runtime."""

    name: str
    enabled: Callable[[], bool]
    discover: Callable[[], list[Dictionary]]


def discover_from_sources(sources: Iterable[DictionarySource]) -> list[Dictionary]:
    """Extend discovery with enabled optional sources."""
    discovered: list[Dictionary] = []
    for source in sources:
        if source.enabled():
            discovered.extend(source.discover())
    return discovered
