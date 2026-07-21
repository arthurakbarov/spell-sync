"""Backward-compatible re-exports for resolved runtime."""

from __future__ import annotations

from .resolved_runtime import ProjectRuntimeMismatchError, ResolvedRuntime

ValidatedRuntime = ResolvedRuntime

__all__ = [
    "ProjectRuntimeMismatchError",
    "ResolvedRuntime",
    "ValidatedRuntime",
]
