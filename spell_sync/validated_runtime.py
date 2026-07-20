"""Backward-compatible re-exports for resolved runtime."""

from __future__ import annotations

from .resolved_runtime import (
    ProjectRuntimeMismatchError,
    ResolvedRuntime,
    build_resolved_runtime,
)

ValidatedRuntime = ResolvedRuntime
build_validated_runtime = build_resolved_runtime

__all__ = [
    "ProjectRuntimeMismatchError",
    "ResolvedRuntime",
    "ValidatedRuntime",
    "build_resolved_runtime",
    "build_validated_runtime",
]
