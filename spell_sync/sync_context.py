"""Immutable runtime context for one dictionary operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .dictionaries import Dictionary
from .project import ProjectContext
from .runtime_settings import RuntimeSettings


@dataclass(frozen=True)
class RuntimeContext(ProjectContext):
    """Wordlist, typed settings, and dictionary targets for one command."""

    settings: RuntimeSettings
    dictionaries: tuple[Dictionary, ...]
    strict_push: bool = False

    @property
    def wordlist_file(self) -> Path:
        return self.wordlist

    @property
    def wordlist_str(self) -> str:
        return str(self.wordlist)

    def dictionary_names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.dictionaries)

    @classmethod
    def build(  # type: ignore[override]
        cls,
        wordlist: Path | str,
        dictionaries: Sequence[Dictionary],
        *,
        settings: RuntimeSettings,
        strict_push: bool = False,
    ) -> RuntimeContext:
        wl = Path(wordlist)
        project = ProjectContext.build(wl)
        return cls(
            wordlist=wl,
            project_dir=project.project_dir,
            config_paths=project.config_paths,
            settings=settings,
            dictionaries=tuple(dictionaries),
            strict_push=strict_push,
        )


def as_dictionary_list(dictionaries: Iterable[Dictionary]) -> list[Dictionary]:
    """Copy for APIs that still expect a mutable list."""
    return list(dictionaries)
