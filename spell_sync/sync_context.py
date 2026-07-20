"""Immutable runtime context for one dictionary operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

from .dictionaries import Dictionary, discover_dictionaries
from .paths import wordlist_path
from .project import ProjectContext
from .settings import load_config_result

if TYPE_CHECKING:
    from .validated_runtime import ValidatedRuntime

RuntimeConfig = dict[str, dict[str, object]]


@dataclass(frozen=True)
class RuntimeContext(ProjectContext):
    """Wordlist, adjacent project config, and dictionary targets for one command."""

    config: RuntimeConfig
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
    def build(
        cls,
        wordlist: Path | str | None = None,
        dictionaries: Sequence[Dictionary] | None = None,
        *,
        config: Mapping[str, Mapping[str, object]] | None = None,
        strict_push: bool = False,
    ) -> RuntimeContext:
        wl = Path(wordlist) if wordlist is not None else wordlist_path()
        project = ProjectContext.build(wl)
        if config is None:
            result = load_config_result(wordlist=wl, reload=True)
            cfg: RuntimeConfig = dict(result.config) if result.config is not None else {}
        else:
            cfg = {section: dict(values) for section, values in config.items()}
        if dictionaries is not None:
            dicts = tuple(dictionaries)
        else:
            dicts = tuple(discover_dictionaries(cfg))
        return cls(
            wordlist=wl,
            project_dir=project.project_dir,
            config_paths=project.config_paths,
            config=cfg,
            dictionaries=dicts,
            strict_push=strict_push,
        )


def runtime_context_for(
    wordlist: Path,
    *,
    strict_push: bool = False,
    validated: ValidatedRuntime | None = None,
) -> RuntimeContext:
    """Build context from effective wordlist; config is adjacent to wordlist."""
    if validated is not None:
        return validated.context
    wl = wordlist
    project_ctx = ProjectContext.build(wl)
    result = load_config_result(wordlist=wl, reload=True)
    config: RuntimeConfig = dict(result.config) if result.config is not None else {}
    dicts = tuple(discover_dictionaries(config))
    return RuntimeContext(
        wordlist=wl,
        project_dir=project_ctx.project_dir,
        config_paths=project_ctx.config_paths,
        config=config,
        dictionaries=dicts,
        strict_push=strict_push,
    )


def as_dictionary_list(dictionaries: Iterable[Dictionary]) -> list[Dictionary]:
    """Copy for APIs that still expect a mutable list."""
    return list(dictionaries)
