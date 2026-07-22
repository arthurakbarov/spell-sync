"""Parent gate orchestration with linked child spans."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .controller import ExecutionController
from .history import HistoryStore
from .models import ExecutionPlan, ExecutionStatus, SpanRecord
from .registry import (
    REGISTRY_REL_PATH,
    load_registry,
)
from .reporting import print_result
from .session import record_session_event


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ActiveGate:
    parent_plan: ExecutionPlan
    parent_span_id: str
    started_monotonic: float
    started_at: str
    parent_hard_deadline: float
    child_duration_sum: float = 0.0
    active_child: str | None = None
    stopped: bool = False
    failure_child: str | None = None
    finalized: bool = False
    terminal_status: str | None = None
    terminal_exit_code: int | None = None
    terminal_timing: dict[str, object] | None = None


@dataclass
class GateController(ExecutionController):
    """Execution controller with parent gate lifecycle."""

    _active_gate: ActiveGate | None = field(default=None, init=False, repr=False)

    @classmethod
    def open_gate_controller(
        cls, root: Path, *, enforce_hard: bool = True, enforce_stall: bool = False
    ) -> GateController:
        registry = load_registry(root / REGISTRY_REL_PATH)
        history = HistoryStore.open()
        return cls(
            root=root,
            registry=registry,
            history=history,
            enforce_hard=enforce_hard,
            enforce_stall=enforce_stall,
        )

    def _parent_remaining(self, gate: ActiveGate) -> float:
        return max(0.0, gate.parent_hard_deadline - time.monotonic())

    def _parent_expired(self, gate: ActiveGate) -> bool:
        return time.monotonic() >= gate.parent_hard_deadline

    def begin_gate(
        self,
        *,
        execution_id: str,
        command: list[str],
        mode: str,
        required: bool = True,
        **kwargs: Any,
    ) -> tuple[ActiveGate | None, str]:
        plan, state = self.prepare_plan(
            execution_id=execution_id,
            command=command,
            mode=mode,
            required=required,
            **kwargs,
        )
        if plan is None:
            return None, state
        started_monotonic = time.monotonic()
        parent_span_id = self.history.new_span_id()
        gate = ActiveGate(
            parent_plan=plan,
            parent_span_id=parent_span_id,
            started_monotonic=started_monotonic,
            started_at=_utc_now(),
            parent_hard_deadline=started_monotonic + plan.hard_seconds,
        )
        self._active_gate = gate
        self._persist_plan(plan)
        print(f"EXECUTION_GATE={execution_id}")
        print(f"EXECUTION_GATE_RUN_ID={plan.run_id}")
        print(f"EXECUTION_GATE_SPAN_ID={gate.parent_span_id}")
        print(f"EXECUTION_GATE_HARD_SECONDS={plan.hard_seconds}")
        print("EXECUTION_PARENT_HARD_SUPERVISION=active")
        return gate, "run"

    def run_child(
        self,
        gate: ActiveGate,
        *,
        child_execution_id: str,
        command: list[str],
        mode: str,
        required: bool = True,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> tuple[int, dict[str, object] | None]:
        if gate.finalized or gate.stopped:
            return gate.terminal_exit_code or 1, gate.terminal_timing
        if self._parent_expired(gate):
            gate.stopped = True
            gate.failure_child = child_execution_id
            return 124, None
        gate.active_child = child_execution_id
        self.history.update_active_child(
            gate.parent_plan.normalized_signature,
            child_execution_id,
        )
        child_plan, state = self.prepare_plan(
            execution_id=child_execution_id,
            command=command,
            mode=mode,
            required=required,
            run_id_override=gate.parent_plan.run_id,
            **kwargs,
        )
        if child_plan is None:
            if state == ExecutionStatus.REUSED.value:
                return 0, {
                    "result": ExecutionStatus.REUSED.value,
                    "executionId": child_execution_id,
                }
            gate.stopped = True
            gate.failure_child = child_execution_id
            return 1, None
        parent_remaining = self._parent_remaining(gate)
        effective_hard = min(child_plan.hard_seconds, parent_remaining)
        exit_code, timing = self.run(
            child_plan,
            command,
            cwd=cwd,
            env=env,
            active_child=child_execution_id,
            parent_span_id=gate.parent_span_id,
            parent_run_id=gate.parent_plan.run_id,
            release_lease=True,
            parent_deadline_monotonic=gate.parent_hard_deadline,
            hard_seconds_override=max(0.001, effective_hard),
        )
        if timing is not None:
            gate.child_duration_sum += float(timing.get("actualSeconds", 0.0))
            result = str(timing.get("result", ""))
            if result in {"timeout-hard", "timeout-stall", "failed"} and exit_code != 0:
                gate.stopped = True
                gate.failure_child = child_execution_id
            elif exit_code != 0:
                gate.stopped = True
                gate.failure_child = child_execution_id
        elif exit_code != 0:
            gate.stopped = True
            gate.failure_child = child_execution_id
        return exit_code, timing

    def finish_gate(
        self,
        gate: ActiveGate,
        *,
        exit_code: int,
        status: ExecutionStatus | None = None,
    ) -> dict[str, object]:
        if gate.finalized:
            if gate.terminal_timing is None:
                raise RuntimeError("gate finalized without terminal timing")
            return gate.terminal_timing

        ended_monotonic = time.monotonic()
        wall_seconds = ended_monotonic - gate.started_monotonic
        ended_at = _utc_now()
        plan = gate.parent_plan
        if status is None:
            if exit_code == 130:
                status = ExecutionStatus.INTERRUPTED
            elif exit_code == 124 or (
                self._parent_expired(gate) and gate.failure_child is not None
            ):
                status = ExecutionStatus.TIMEOUT_HARD
            elif exit_code == 0:
                status = (
                    ExecutionStatus.SUCCESS_SLOW
                    if wall_seconds > plan.soft_seconds
                    else ExecutionStatus.SUCCESS
                )
            elif gate.failure_child:
                status = ExecutionStatus.FAILED
            else:
                status = ExecutionStatus.FAILED
        accepted = (
            status == ExecutionStatus.SUCCESS
            and wall_seconds <= plan.soft_seconds
            and exit_code == 0
        )
        overhead = max(0.0, wall_seconds - gate.child_duration_sum)
        parent_prediction = self.history.fetch_profile_durations(
            execution_id=plan.execution_id, limit=30
        )
        sample_count = len(parent_prediction)
        confidence = plan.confidence
        if sample_count >= 10:
            confidence = "high"
        elif sample_count >= 3:
            confidence = "medium"
        record = SpanRecord(
            run_id=plan.run_id,
            span_id=gate.parent_span_id,
            parent_span_id=None,
            execution_id=plan.execution_id,
            profile_id=plan.profile_id,
            normalized_signature=plan.normalized_signature,
            workload_fingerprint=plan.workload_fingerprint,
            policy_fingerprint=plan.policy_fingerprint,
            start_time=gate.started_at,
            end_time=ended_at,
            duration_seconds=wall_seconds,
            exit_code=exit_code,
            status=status.value,
            expected_seconds=plan.expected_seconds,
            soft_seconds=plan.soft_seconds,
            stall_seconds=plan.stall_seconds,
            hard_seconds=plan.hard_seconds,
            prediction_source=plan.prediction_source,
            confidence=confidence,
            sample_count=sample_count,
            progress_event_count=0,
            maximum_progress_gap=0.0,
            active_child_at_end=gate.failure_child or gate.active_child,
            accepted_for_learning=accepted,
            quarantine_reason="soft-overrun" if status == ExecutionStatus.SUCCESS_SLOW else None,
            diagnostic_bundle=None,
        )
        self.history.insert_span(record, context_signature=plan.context_signature)
        self.history.release_lease(plan.normalized_signature)
        category = "full-ci" if plan.profile_id == "full-ci" else plan.profile_id
        record_session_event(category=category, duration_seconds=wall_seconds)
        timing: dict[str, object] = {
            **plan.to_json_dict(),
            "actualSeconds": round(wall_seconds, 2),
            "childDurationSum": round(gate.child_duration_sum, 2),
            "orchestrationOverhead": round(overhead, 2),
            "unattributedDuration": round(overhead, 2),
            "result": status.value,
            "activeChildAtEnd": gate.failure_child or gate.active_child,
            "parentSpanId": gate.parent_span_id,
        }
        print_result(
            result=status.value,
            exit_code=exit_code,
            duration=wall_seconds,
            active_child=gate.failure_child or gate.active_child,
            history_updated=not self.history.degraded,
            learning_accepted=accepted,
        )
        gate.finalized = True
        gate.terminal_status = status.value
        gate.terminal_exit_code = exit_code
        gate.terminal_timing = timing
        self._active_gate = None
        return timing
