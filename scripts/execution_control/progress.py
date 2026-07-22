"""Progress contracts for stall detection."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_PYTEST_NODE_RE = re.compile(
    r"^(?P<path>tests/\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)"
)
_PYTEST_COLLECT_RE = re.compile(r"^tests/\S+::\S+\s")
_CI_CHILD_RE = re.compile(
    r"(?P<child>[a-z0-9._:-]+)\s*:\s*(passed|failed|started|completed|exit=)",
    re.I,
)
_PHASE_RE = re.compile(r"^(===|---)\s+.+")
_ARTIFACT_RE = re.compile(r"(SNAPSHOT_|CI_RESULT=|TEST_RUN_RESULT=|EXECUTION_GATE=|archive-check=)")


@dataclass
class ProgressTracker:
    contract_id: str
    last_progress_at: float = field(default_factory=time.monotonic)
    last_sequence: int = -1
    last_node_id: str = ""
    last_child_id: str = ""
    last_phase_id: str = ""
    last_artifact_state: str = ""
    event_count: int = 0
    maximum_gap: float = 0.0

    def observe_line(self, line: str) -> None:
        now = time.monotonic()
        if self.contract_id == "pytest-node-transition":
            match = _PYTEST_NODE_RE.match(line.strip())
            if match:
                node_id = match.group("path")
                if node_id != self.last_node_id:
                    self.last_node_id = node_id
                    self._mark_progress(now)
                return
            if _PYTEST_COLLECT_RE.match(line.strip()):
                node_id = line.strip().split()[0]
                if node_id != self.last_node_id:
                    self.last_node_id = node_id
                    self._mark_progress(now)
            return

        if self.contract_id == "ci-child-transition":
            match = _CI_CHILD_RE.search(line)
            if match:
                child_id = match.group("child")
                if child_id != self.last_child_id:
                    self.last_child_id = child_id
                    self._mark_progress(now)
            return

        if self.contract_id == "structured-phase-transition":
            match = _PHASE_RE.match(line.strip())
            if match:
                phase_id = line.strip()
                if phase_id != self.last_phase_id:
                    self.last_phase_id = phase_id
                    self._mark_progress(now)
            if re.search(r"\bpassed\b", line, re.I) and "===" in line:
                phase_id = line.strip()
                if phase_id != self.last_phase_id:
                    self.last_phase_id = phase_id
                    self._mark_progress(now)
            return

        if self.contract_id == "artifact-state-transition":
            match = _ARTIFACT_RE.search(line)
            if match:
                state = match.group(0)
                if state != self.last_artifact_state:
                    self.last_artifact_state = state
                    self._mark_progress(now)

    def observe_child_event(self, child_id: str) -> None:
        if child_id != self.last_child_id:
            self.last_child_id = child_id
            self._mark_progress(time.monotonic())

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
