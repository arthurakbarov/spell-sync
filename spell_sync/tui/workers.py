"""Worker token tracking for non-blocking TUI loads."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class _MountedNode(Protocol):
    @property
    def is_mounted(self) -> bool: ...


class LoadTokenMixin:
    """Ignore stale worker results after a newer refresh starts."""

    _load_generation = 0

    def _begin_load(self) -> int:
        self._load_generation += 1
        return self._load_generation

    def _is_current_load(self, token: int) -> bool:
        mounted = isinstance(self, _MountedNode) and self.is_mounted
        return token == self._load_generation and mounted
