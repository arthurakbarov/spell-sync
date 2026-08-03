"""Session accounting delta tests."""

from __future__ import annotations

import itertools
import json

from scripts.execution_control.session import record_session_event
from scripts.execution_control.state_paths import state_root


class _FakeClock:
    def __init__(self, values: list[float]):
        self.values = itertools.cycle(values)

    def monotonic(self) -> float:
        return next(self.values)


def test_session_elapsed_uses_deltas_not_event_sum(monkeypatch, isolated_state_dir):
    del isolated_state_dir
    clock = _FakeClock([0.0, 10.0, 20.0, 30.0])
    monkeypatch.setattr("scripts.execution_control.session.time.monotonic", clock.monotonic)
    record_session_event(category="focused", duration_seconds=1.0)
    record_session_event(category="focused", duration_seconds=1.0)
    record_session_event(category="focused", duration_seconds=1.0)
    payload = json.loads((state_root() / "session.json").read_text(encoding="utf-8"))
    assert payload["editSeconds"] == 30.0
