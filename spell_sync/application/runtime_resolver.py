"""Explicit runtime resolution for the application layer."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace

from ..application._runtime_factory import _build_resolved_runtime
from ..resolved_runtime import ProjectRuntimeMismatchError, ResolvedRuntime
from ..sync_run import SyncRun
from .mutation_scope import mutation_scope_for
from .project_resolution import resolve_project_wordlist
from .requests import ProjectRef

__all__ = [
    "ProjectRuntimeMismatchError",
    "ResolvedRuntime",
    "RuntimeResolver",
]


@dataclass(frozen=True, slots=True)
class RuntimeResolver:
    bound: ResolvedRuntime | None = None

    def _assert_bound_project(self, project: ProjectRef) -> None:
        if self.bound is None:
            return
        self.bound.assert_wordlist(resolve_project_wordlist(project))

    def resolve_read(
        self,
        project: ProjectRef,
        *,
        strict_push: bool = False,
        validate_journal_wordlist: bool = False,
    ) -> ResolvedRuntime:
        if self.bound is not None:
            self._assert_bound_project(project)
            if strict_push != self.bound.context.strict_push:
                ctx = replace(self.bound.context, strict_push=strict_push)
                return replace(self.bound, context=ctx)
            return self.bound
        wordlist = resolve_project_wordlist(project)
        return _build_resolved_runtime(
            wordlist,
            strict_push_override=strict_push,
            validate_journal_wordlist=validate_journal_wordlist,
        )

    def validated(
        self,
        project: ProjectRef,
        *,
        strict_push: bool = False,
        validate_journal_wordlist: bool = False,
    ) -> ResolvedRuntime:
        return self.resolve_read(
            project,
            strict_push=strict_push,
            validate_journal_wordlist=validate_journal_wordlist,
        )

    def sync_run(self, project: ProjectRef, *, strict_push: bool = False) -> SyncRun:
        resolved = self.resolve_read(project, strict_push=strict_push)
        return SyncRun(context=resolved.context)

    @contextmanager
    def mutation_scope(
        self,
        project: ProjectRef,
        command: str,
        *,
        allow_unfinished_journal: bool = False,
        strict_push_override: bool | None = None,
        json_output: bool = False,
    ) -> Iterator[ResolvedRuntime | int]:
        wordlist = resolve_project_wordlist(project)
        with mutation_scope_for(
            wordlist,
            command,
            allow_unfinished_journal=allow_unfinished_journal,
            strict_push_override=strict_push_override,
            json_output=json_output,
        ) as scope:
            yield scope
