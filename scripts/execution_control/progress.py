"""Progress contracts for stall detection."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class ProgressTracker:
    contract_id: str
    last_progress_at: float = field(default_factory=time.monotonic)
    last_sequence: int = -1
    last_line_hash: str = ""
    repeated_line_count: int = 0
    event_count: int = 0
    maximum_gap: float = 0.0
    _last_gap_start: float = field(default_factory=time.monotonic)

    def observe_line(self, line: str) -> None:
        now = time.monotonic()
        line_hash = str(hash(line.strip()))
        if self.contract_id == "pytest-node-transition":
            if " PASSED" in line or " FAILED" in line or " ERROR" in line:
                self._mark_progress(now)
            elif line.startswith("tests/") or "::test_" in line:
                self._mark_progress(now)
        elif self.contract_id == "ci-child-transition":
            if re.search(r":\s*(passed|failed|exit=)", line, re.I):
                self._mark_progress(now)
        elif self.contract_id == "structured-phase-transition":
            if line.startswith("===") or line.startswith("---") or " passed" in line.lower():
                self._mark_progress(now)
        elif self.contract_id == "artifact-state-transition":
            if "SNAPSHOT_" in line or "CI_RESULT=" in line or "TEST_RUN_RESULT=" in line:
                self._mark_progress(now)

        if line_hash == self.last_line_hash:
            self.repeated_line_count += 1
        else:
            self.repeated_line_count = 0
            self.last_line_hash = line_hash
        if self.repeated_line_count >= 50:
            return
        if line.strip():
            self._mark_progress(now)

    def observe_child_event(self, child_id: str) -> None:
        self._mark_progress(time.monotonic())
        _ = child_id

    def observe_sequence(self, sequence: int) -> None:
        if sequence > self.last_sequence:
            self.last_sequence = sequence
            self._mark_progress(time.monotonic())

    def _mark_progress(self, now: float) -> None:
        gap = now - self.last_progress_at
        if gap > self.maximum_gap:
            self.maximum_gap = gap
        self.last_progress_at = now
        self.event_count += 1

    def progress_age(self) -> float:
        return time.monotonic() - self.last_progress_at


def create_tracker(contract_id: str | None) -> ProgressTracker | None:
    if not contract_id:
        return None
    return ProgressTracker(contract_id=contract_id)
