"""Single config and journal load under operation lock."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dictionaries import discover_dictionaries
from .project import ProjectContext
from .push_journal import JournalLoadResult, load_journal_result
from .settings import ConfigLoadResult, bind_active_settings, load_config_result
from .sync_context import RuntimeConfig, RuntimeContext


@dataclass(frozen=True)
class ValidatedRuntime:
    context: RuntimeContext
    config_result: ConfigLoadResult
    journal_result: JournalLoadResult


def build_validated_runtime(
    wordlist: Path,
    *,
    strict_push: bool = False,
    validate_journal_wordlist: bool = False,
) -> ValidatedRuntime:
    project = ProjectContext.build(wordlist)
    config_result = load_config_result(wordlist=wordlist, reload=True)
    config: RuntimeConfig = dict(config_result.config) if config_result.config is not None else {}
    bind_active_settings(config)
    dicts = tuple(discover_dictionaries(config))
    context = RuntimeContext(
        wordlist=wordlist,
        project_dir=project.project_dir,
        config_paths=project.config_paths,
        config=config,
        dictionaries=dicts,
        strict_push=strict_push,
    )
    journal_result = load_journal_result(
        wordlist,
        validate_wordlist=validate_journal_wordlist,
    )
    return ValidatedRuntime(context, config_result, journal_result)
