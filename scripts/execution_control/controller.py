"""Execution controller: immutable plans, bounded subprocess runs, history."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .admission import assess_admission
from .context import build_context
from .diagnostics import collect_timeout_bundle
from .history import HistoryStore
from .models import ExecutionPlan, ExecutionStatus, SpanRecord
from .paths import plan_artifact_path
from .process_tree import ProcessResult, run_owned_command
from .progress import create_tracker
from .registry import (
    REGISTRY_REL_PATH,
    ExecutionBudgetRegistry,
    load_registry,
    profile_for_execution_id,
)
from .reporting import print_plan, print_result
from .session import check_performance_regression, record_session_event


@dataclass
class ExecutionController:
    root: Path
    registry: ExecutionBudgetRegistry
    history: HistoryStore
    enforce_hard: bool = True
    enforce_stall: bool = False

    @classmethod
    def open(
        cls, root: Path, *, enforce_hard: bool = True, enforce_stall: bool = False
    ) -> ExecutionController:
        registry = load_registry(root / REGISTRY_REL_PATH)
        history = HistoryStore.open()
        return cls(
            root=root,
            registry=registry,
            history=history,
            enforce_hard=enforce_hard,
            enforce_stall=enforce_stall,
        )

    def prepare_plan(
        self,
        *,
        execution_id: str,
        command: list[str],
        mode: str,
        required: bool = False,
        test_file_count: int = 0,
        test_node_count: int = 0,
        cluster_ids: tuple[str, ...] = (),
        coverage: bool = False,
        tui: bool = False,
        packaging: bool = False,
    ) -> tuple[ExecutionPlan | None, str]:
        profile = profile_for_execution_id(self.registry, execution_id)
        admission, plan = assess_admission(
            self.root,
            execution_id=execution_id,
            profile=profile,
            registry=self.registry,
            history=self.history,
            command=command,
            mode=mode,
            required=required,
            test_file_count=test_file_count,
            test_node_count=test_node_count,
            cluster_ids=cluster_ids,
            coverage=coverage,
            tui=tui,
            packaging=packaging,
        )
        if admission.decision.value == "reuse":
            print_result(
                result=ExecutionStatus.REUSED.value,
                exit_code=0,
                duration=0.0,
                active_child=None,
                history_updated=False,
                learning_accepted=False,
            )
            return None, ExecutionStatus.REUSED.value
        if admission.decision.value == "reject-duplicate":
            return None, ExecutionStatus.BLOCKED_DUPLICATE.value
        assert plan is not None
        acquired, owner = self.history.acquire_lease(
            normalized_signature=plan.normalized_signature,
            run_id=plan.run_id,
            execution_id=plan.execution_id,
            owner_pid=os.getpid(),
        )
        if not acquired:
            print("EXECUTION_RESULT=blocked")
            print("EXECUTION_FAILED_ID=execution.duplicate-active")
            if owner:
                print(f"EXECUTION_OWNER_PID={owner.get('owner_pid', '')}")
            return None, ExecutionStatus.BLOCKED_DUPLICATE.value
        self._persist_plan(plan)
        print_plan(plan)
        return plan, "run"

    def run(
        self,
        plan: ExecutionPlan,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        active_child: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        tracker = create_tracker(plan.progress_contract_id)
        result = run_owned_command(
            command,
            cwd=cwd or self.root,
            env=env,
            hard_seconds=plan.hard_seconds,
            soft_seconds=plan.soft_seconds,
            stall_seconds=plan.stall_seconds,
            termination_grace_seconds=plan.termination_grace_seconds,
            tracker=tracker,
            enforce_hard=self.enforce_hard,
            enforce_stall=self.enforce_stall,
        )
        status, accepted, quarantine = self._classify_result(plan, result)
        diagnostic_bundle = None
        if result.timed_out:
            diagnostic_bundle = collect_timeout_bundle(
                plan=plan,
                result=result,
                active_child=active_child or plan.execution_id,
                timeout_kind=result.timeout_kind or "hard",
            )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        record = SpanRecord(
            run_id=plan.run_id,
            span_id=self.history.new_span_id(),
            parent_span_id=None,
            execution_id=plan.execution_id,
            profile_id=plan.profile_id,
            normalized_signature=plan.normalized_signature,
            workload_fingerprint=plan.workload_fingerprint,
            policy_fingerprint=plan.policy_fingerprint,
            start_time=now,
            end_time=now,
            duration_seconds=result.duration_seconds,
            exit_code=result.exit_code,
            status=status.value,
            expected_seconds=plan.expected_seconds,
            soft_seconds=plan.soft_seconds,
            stall_seconds=plan.stall_seconds,
            hard_seconds=plan.hard_seconds,
            prediction_source=plan.prediction_source,
            confidence=plan.confidence,
            sample_count=plan.sample_count,
            progress_event_count=result.progress_event_count,
            maximum_progress_gap=result.maximum_progress_gap,
            active_child_at_end=active_child,
            accepted_for_learning=accepted,
            quarantine_reason=quarantine,
            diagnostic_bundle=diagnostic_bundle,
        )
        context = build_context(execution_mode=plan.profile_id)
        self.history.insert_span(record, context_signature=context.signature())
        self.history.release_lease(plan.normalized_signature)
        category = "full-ci" if plan.profile_id == "full-ci" else plan.profile_id
        if status == ExecutionStatus.REUSED:
            record_session_event(
                category=category, duration_seconds=0.0, reused_saved=plan.expected_seconds
            )
        else:
            record_session_event(category=category, duration_seconds=result.duration_seconds)
        if accepted:
            prior = self.history.fetch_learning_durations(
                execution_id=plan.execution_id,
                workload_fingerprint=plan.workload_fingerprint,
                limit=10,
            )
            if len(prior) >= 6:
                old = prior[5:]
                new = prior[:5]
                if old and new:
                    from statistics import median

                    check_performance_regression(
                        execution_id=plan.execution_id,
                        workload_fingerprint=plan.workload_fingerprint,
                        old_median=float(median(old)),
                        new_median=float(median(new)),
                        old_count=len(old),
                        new_count=len(new),
                    )
        print_result(
            result=status.value,
            exit_code=result.exit_code,
            duration=result.duration_seconds,
            active_child=active_child,
            history_updated=not self.history.degraded,
            learning_accepted=accepted,
        )
        timing = {
            **plan.to_json_dict(),
            "actualSeconds": result.duration_seconds,
            "result": status.value,
            "stdoutTail": result.stdout_tail,
            "stderrTail": result.stderr_tail,
        }
        return result.exit_code, timing

    def _classify_result(
        self,
        plan: ExecutionPlan,
        result: ProcessResult,
    ) -> tuple[ExecutionStatus, bool, str | None]:
        if result.timed_out:
            if result.timeout_kind == "stall":
                return ExecutionStatus.TIMEOUT_STALL, False, "timeout-stall"
            return ExecutionStatus.TIMEOUT_HARD, False, "timeout-hard"
        if result.exit_code != 0:
            return ExecutionStatus.FAILED, False, None
        if result.duration_seconds > plan.soft_seconds:
            return ExecutionStatus.SUCCESS_SLOW, False, "soft-overrun"
        if result.duration_seconds <= plan.soft_seconds:
            return ExecutionStatus.SUCCESS, True, None
        return ExecutionStatus.SUCCESS, False, None

    def _persist_plan(self, plan: ExecutionPlan) -> None:
        path = plan_artifact_path(plan.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(plan.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def run_monitored_command(
    root: Path,
    *,
    execution_id: str,
    command: list[str],
    mode: str,
    required: bool = False,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    test_file_count: int = 0,
    test_node_count: int = 0,
    cluster_ids: tuple[str, ...] = (),
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
    enforce_hard: bool = True,
    enforce_stall: bool = False,
) -> tuple[int, dict[str, object] | None]:
    controller = ExecutionController.open(
        root, enforce_hard=enforce_hard, enforce_stall=enforce_stall
    )
    plan, state = controller.prepare_plan(
        execution_id=execution_id,
        command=command,
        mode=mode,
        required=required,
        test_file_count=test_file_count,
        test_node_count=test_node_count,
        cluster_ids=cluster_ids,
        coverage=coverage,
        tui=tui,
        packaging=packaging,
    )
    if plan is None:
        return 0 if state == ExecutionStatus.REUSED.value else 1, None
    exit_code, timing = controller.run(plan, command, cwd=cwd, env=env, active_child=execution_id)
    return exit_code, timing
