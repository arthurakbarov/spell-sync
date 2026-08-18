"""Worker token tracking for non-blocking TUI loads."""

from textual.worker import Worker, WorkerState

_TERMINAL_WORKER_STATES = frozenset(
    {
        WorkerState.SUCCESS,
        WorkerState.ERROR,
        WorkerState.CANCELLED,
    }
)


def is_terminal_worker_state(state: WorkerState) -> bool:
    """True for SUCCESS / ERROR / CANCELLED (not PENDING or RUNNING)."""
    return state in _TERMINAL_WORKER_STATES


class LoadTokenMixin:
    """Ignore stale worker results after a newer refresh starts.

    Textual 8 delivers ``Worker.StateChanged`` to ``on_worker_state_changed``
    (message namespace ``worker``). Route terminal states to the existing
    per-worker handlers named ``on_<worker.name>_state_changed``.

    Pending/running must not be forwarded: handlers that only skip ``RUNNING``
    still treat ``PENDING`` as failure and clear in-progress flags too early.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._load_generation = 0

    def _begin_load(self) -> int:
        self._load_generation += 1
        return self._load_generation

    def _is_current_load(self, token: int) -> bool:
        mounted = getattr(self, "is_mounted", False)
        return token == self._load_generation and bool(mounted)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state not in _TERMINAL_WORKER_STATES:
            return
        handler = getattr(self, f"on_{event.worker.name}_state_changed", None)
        if callable(handler):
            handler(event)
