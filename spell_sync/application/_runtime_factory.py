"""Private runtime construction for application resolution paths."""

from pathlib import Path

from ..dictionaries import discover_dictionaries
from ..project import ProjectContext
from ..push_journal import load_journal_result
from ..resolved_runtime import ResolvedRuntime
from ..runtime_identity import build_runtime_identity
from ..settings import load_config_result
from ..sync_context import RuntimeContext


def _build_resolved_runtime(
    wordlist: Path,
    *,
    strict_push_override: bool | None = None,
    validate_journal_wordlist: bool = False,
) -> ResolvedRuntime:
    project = ProjectContext.build(wordlist)
    config_result = load_config_result(wordlist=wordlist)
    settings = config_result.runtime_settings()
    effective_strict = (
        strict_push_override if strict_push_override is not None else settings.push.strict
    )
    dicts = tuple(discover_dictionaries(settings))
    context = RuntimeContext(
        wordlist=wordlist,
        project_dir=project.project_dir,
        config_path=project.config_path,
        settings=settings,
        dictionaries=dicts,
        strict_push=effective_strict,
    )
    journal_result = load_journal_result(
        wordlist,
        validate_wordlist=validate_journal_wordlist,
    )
    identity = build_runtime_identity(context, config_result=config_result)
    return ResolvedRuntime(context, config_result, journal_result, identity)
