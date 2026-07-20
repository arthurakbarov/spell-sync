"""Construct resolved runtime from wordlist path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dictionaries import discover_dictionaries
from .project import ProjectContext
from .push_journal import JournalLoadResult, load_journal_result
from .settings import ConfigLoadResult, load_config_result
from .sync_context import RuntimeContext


class ProjectRuntimeMismatchError(RuntimeError):
    """Bound runtime does not match the requested project."""


@dataclass(frozen=True, slots=True)
class ResolvedRuntime:
    context: RuntimeContext
    config_result: ConfigLoadResult
    journal_result: JournalLoadResult

    def assert_wordlist(self, wordlist: Path) -> None:
        if self.context.wordlist.resolve() != wordlist.resolve():
            raise ProjectRuntimeMismatchError(
                "bound runtime wordlist does not match requested project"
            )


def build_resolved_runtime(
    wordlist: Path,
    *,
    strict_push: bool = False,
    validate_journal_wordlist: bool = False,
) -> ResolvedRuntime:
    project = ProjectContext.build(wordlist)
    config_result = load_config_result(wordlist=wordlist)
    settings = config_result.runtime_settings()
    dicts = tuple(discover_dictionaries(settings))
    context = RuntimeContext(
        wordlist=wordlist,
        project_dir=project.project_dir,
        config_paths=project.config_paths,
        settings=settings,
        dictionaries=dicts,
        strict_push=strict_push,
    )
    journal_result = load_journal_result(
        wordlist,
        validate_wordlist=validate_journal_wordlist,
    )
    return ResolvedRuntime(context, config_result, journal_result)
