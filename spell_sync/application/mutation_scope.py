"""Mutation scope: lock, config, and journal validation without module globals."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..application._runtime_factory import _build_resolved_runtime
from ..mutation_guards import (
    invalid_config_exit_from_scope,
    operation_lock_scope_for,
    unfinished_journal_exit_from_result_for,
)
from ..resolved_runtime import ResolvedRuntime

MutationScopeResult = ResolvedRuntime | int


@contextmanager
def mutation_scope_for(
    wordlist: Path,
    command: str,
    *,
    allow_unfinished_journal: bool = False,
    strict_push_override: bool | None = None,
    json_output: bool = False,
) -> Iterator[MutationScopeResult]:
    """Acquire lock, then load config and journal once for mutating commands."""
    with operation_lock_scope_for(wordlist, command, json_output=json_output) as lock_exit:
        if lock_exit is not None:
            yield lock_exit
            return
        resolved = _build_resolved_runtime(
            wordlist,
            strict_push_override=strict_push_override,
        )
        config_exit = invalid_config_exit_from_scope(
            command,
            resolved.config_result,
            json_output=json_output,
        )
        if config_exit is not None:
            yield config_exit
            return
        if not allow_unfinished_journal:
            journal_exit = unfinished_journal_exit_from_result_for(
                command,
                resolved.journal_result,
                json_output=json_output,
                wordlist=wordlist,
            )
            if journal_exit is not None:
                yield journal_exit
                return
        yield resolved
