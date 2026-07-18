"""Worker token tracking for non-blocking TUI loads."""

from __future__ import annotations


class LoadTokenMixin:
    """Ignore stale worker results after a newer refresh starts."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._load_generation = 0

    def _begin_load(self) -> int:
        self._load_generation += 1
        return self._load_generation

    def _is_current_load(self, token: int) -> bool:
        mounted = getattr(self, "is_mounted", False)
        return token == self._load_generation and bool(mounted)
