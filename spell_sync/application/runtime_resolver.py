"""Explicit runtime resolution for the application layer."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..sync_run import SyncRun, sync_run_for
from ..validated_runtime import ValidatedRuntime, build_validated_runtime
from .project_resolution import resolve_project_wordlist
from .requests import ProjectRef


@dataclass(frozen=True, slots=True)
class RuntimeResolver:
    bound: ValidatedRuntime | None = None

    def validated(
        self,
        project: ProjectRef,
        *,
        strict_push: bool = False,
        validate_journal_wordlist: bool = False,
    ) -> ValidatedRuntime:
        if self.bound is not None:
            return self.bound
        wordlist = resolve_project_wordlist(project)
        return build_validated_runtime(
            wordlist,
            strict_push=strict_push,
            validate_journal_wordlist=validate_journal_wordlist,
        )

    def sync_run(self, project: ProjectRef, *, strict_push: bool = False) -> SyncRun:
        if self.bound is not None:
            ctx = self.bound.context
            if strict_push != ctx.strict_push:
                ctx = replace(ctx, strict_push=strict_push)
            return SyncRun(context=ctx)
        return sync_run_for(resolve_project_wordlist(project), strict_push=strict_push)
