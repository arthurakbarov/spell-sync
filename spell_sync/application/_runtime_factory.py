"""Private runtime construction for application resolution paths."""

from __future__ import annotations

from pathlib import Path

from ..dictionaries import discover_dictionaries
from ..project import ProjectContext
from ..push_journal import load_journal_result
from ..resolved_runtime import ResolvedRuntime
from ..settings import load_config_result
from ..sync_context import RuntimeContext


def _build_resolved_runtime(
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
