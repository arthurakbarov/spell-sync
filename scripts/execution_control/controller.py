"""Execution controller: immutable plans, bounded subprocess runs, history."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .admission import assess_admission, narrow_replacement_plan
from .diagnostics import collect_timeout_bundle
from .execution_result import ControlledExecutionResult
from .history import HistoryStore
from .models import AdmissionDecision, ExecutionPlan, ExecutionStatus, SpanRecord
from .paths import plan_artifact_path
from .privacy import sanitize_text, workspace_roots
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
        run_id_override: str | None = None,
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
        if admission.decision == AdmissionDecision.REUSE:
            print_result(
                result=ExecutionStatus.REUSED.value,
                exit_code=0,
                duration=0.0,
                active_child=None,
                history_updated=False,
                learning_accepted=False,
            )
            return None, ExecutionStatus.REUSED.value
        if admission.decision == AdmissionDecision.REJECT_DUPLICATE:
            return None, ExecutionStatus.BLOCKED_DUPLICATE.value
        if admission.decision == AdmissionDecision.NARROW:
            print("EXECUTION_RESULT=blocked")
            print("EXECUTION_FAILED_ID=execution.narrow-admission")
            print(f"EXECUTION_ADMISSION_REASON={admission.reason}")
            replacement = narrow_replacement_plan(
                execution_id=execution_id,
                mode=mode,
                admission=admission,
                plan=plan,
            )
            print(f"EXECUTION_REPLACEMENT_REQUIRED_CHECKS={','.join(replacement.required_checks)}")
            print(f"EXECUTION_REPLACEMENT_DEFERRED_CHECKS={','.join(replacement.deferred_checks)}")
            print(f"EXECUTION_REPLACEMENT_EXECUTION_ID={replacement.suggested_execution_id}")
            print(f"EXECUTION_REPLACEMENT_COMMAND_KEY={replacement.suggested_command_key}")
            print(
                f"EXECUTION_REPLACEMENT_PREDICTED_COST={replacement.predicted_replacement_cost:.2f}"
            )
            if plan is not None:
                self._persist_plan(plan)
                print_plan(plan)
            return None, ExecutionStatus.BLOCKED_ADMISSION.value
        if admission.decision == AdmissionDecision.DEFER_TO_PRE_FINAL:
            print("EXECUTION_RESULT=blocked")
            print("EXECUTION_FAILED_ID=execution.defer-to-pre-final")
            return None, ExecutionStatus.BLOCKED_ADMISSION.value
        if admission.decision == AdmissionDecision.BLOCK_CONTROLLER_ERROR:
            print("EXECUTION_RESULT=blocked")
            print("EXECUTION_FAILED_ID=execution.controller-error")
            return None, ExecutionStatus.BLOCKED_ADMISSION.value
        assert plan is not None
        if run_id_override is not None:
            plan = replace(plan, run_id=run_id_override)
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
                print(f"EXECUTION_PARENT_RUN_ID={owner.get('run_id', '')}")
                print(f"EXECUTION_ACTIVE_CHILD={owner.get('active_child', '')}")
                started_at = str(owner.get("started_at", ""))
                if started_at:
                    try:
                        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                        print(f"EXECUTION_PARENT_ELAPSED_SECONDS={elapsed:.2f}")
                    except ValueError:
                        pass
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
        parent_span_id: str | None = None,
        parent_run_id: str | None = None,
        release_lease: bool = True,
        parent_deadline_monotonic: float | None = None,
        hard_seconds_override: float | None = None,
    ) -> ControlledExecutionResult:
        tracker = create_tracker(plan.progress_contract_id)
        effective_hard = (
            hard_seconds_override if hard_seconds_override is not None else plan.hard_seconds
        )
        if parent_deadline_monotonic is not None:
            parent_remaining = max(0.0, parent_deadline_monotonic - time.monotonic())
            effective_hard = min(effective_hard, parent_remaining)
        roots = workspace_roots(public_root=self.root)
        try:
            result = run_owned_command(
                command,
                cwd=cwd or self.root,
                env=env,
                hard_seconds=max(0.001, effective_hard),
                soft_seconds=plan.soft_seconds,
                stall_seconds=plan.stall_seconds,
                termination_grace_seconds=plan.termination_grace_seconds,
                tracker=tracker,
                enforce_hard=self.enforce_hard,
                enforce_stall=self.enforce_stall,
                parent_deadline_monotonic=parent_deadline_monotonic,
                soft_report_plan=plan,
                active_child=active_child or plan.execution_id,
            )
        except KeyboardInterrupt:
            self._record_interrupt_span(
                plan,
                parent_span_id=parent_span_id,
                parent_run_id=parent_run_id,
                active_child=active_child,
            )
            if release_lease:
                self.history.release_lease(plan.normalized_signature)
            raise
        status, accepted, quarantine = self._classify_result(plan, result)
        diagnostic_bundle = None
        if result.timed_out:
            bundle = collect_timeout_bundle(
                plan=plan,
                result=result,
                active_child=active_child or plan.execution_id,
                timeout_kind=result.timeout_kind or "hard",
                public_root=self.root,
            )
            diagnostic_bundle = bundle.path
            if bundle.incomplete and diagnostic_bundle is None:
                diagnostic_bundle = "diagnostic-incomplete"
        run_id = parent_run_id or plan.run_id
        record = SpanRecord(
            run_id=run_id,
            span_id=self.history.new_span_id(),
            parent_span_id=parent_span_id,
            execution_id=plan.execution_id,
            profile_id=plan.profile_id,
            normalized_signature=plan.normalized_signature,
            workload_fingerprint=plan.workload_fingerprint,
            policy_fingerprint=plan.policy_fingerprint,
            start_time=result.start_time_iso,
            end_time=result.end_time_iso,
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
            environment_signature=plan.environment_signature,
        )
        self.history.insert_span(record, context_signature=plan.context_signature)
        if release_lease:
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
        sanitized_stdout = sanitize_text(result.stdout_tail, workspace_roots=roots)
        sanitized_stderr = sanitize_text(result.stderr_tail, workspace_roots=roots)
        timing = {
            **plan.to_json_dict(),
            "actualSeconds": result.duration_seconds,
            "result": status.value,
            "stdoutTail": sanitized_stdout,
            "stderrTail": sanitized_stderr,
            "spanId": record.span_id,
            "parentSpanId": parent_span_id,
        }
        return ControlledExecutionResult(
            exit_code=result.exit_code,
            raw_stdout_tail=result.stdout_tail,
            raw_stderr_tail=result.stderr_tail,
            sanitized_stdout_tail=sanitized_stdout,
            sanitized_stderr_tail=sanitized_stderr,
            timing=timing,
        )

    def _record_interrupt_span(
        self,
        plan: ExecutionPlan,
        *,
        parent_span_id: str | None,
        parent_run_id: str | None,
        active_child: str | None,
    ) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        record = SpanRecord(
            run_id=parent_run_id or plan.run_id,
            span_id=self.history.new_span_id(),
            parent_span_id=parent_span_id,
            execution_id=plan.execution_id,
            profile_id=plan.profile_id,
            normalized_signature=plan.normalized_signature,
            workload_fingerprint=plan.workload_fingerprint,
            policy_fingerprint=plan.policy_fingerprint,
            start_time=now,
            end_time=now,
            duration_seconds=0.0,
            exit_code=130,
            status=ExecutionStatus.INTERRUPTED.value,
            expected_seconds=plan.expected_seconds,
            soft_seconds=plan.soft_seconds,
            stall_seconds=plan.stall_seconds,
            hard_seconds=plan.hard_seconds,
            prediction_source=plan.prediction_source,
            confidence=plan.confidence,
            sample_count=plan.sample_count,
            progress_event_count=0,
            maximum_progress_gap=0.0,
            active_child_at_end=active_child,
            accepted_for_learning=False,
            quarantine_reason="interrupted",
            diagnostic_bundle=None,
            environment_signature=plan.environment_signature,
        )
        self.history.insert_span(record, context_signature=plan.context_signature)
        print_result(
            result=ExecutionStatus.INTERRUPTED.value,
            exit_code=130,
            duration=0.0,
            active_child=active_child,
            history_updated=not self.history.degraded,
            learning_accepted=False,
        )

    def _classify_result(
        self,
        plan: ExecutionPlan,
        result: ProcessResult,
    ) -> tuple[ExecutionStatus, bool, str | None]:
        if result.interrupted:
            return ExecutionStatus.INTERRUPTED, False, "interrupted"
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
    parent_span_id: str | None = None,
    parent_run_id: str | None = None,
    run_id_override: str | None = None,
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
        run_id_override=run_id_override,
    )
    if plan is None:
        if state == ExecutionStatus.REUSED.value:
            return 0, None
        if state == ExecutionStatus.BLOCKED_ADMISSION.value:
            return 1, {
                "result": ExecutionStatus.BLOCKED_ADMISSION.value,
                "executionId": execution_id,
            }
        return 1, None
    execution = controller.run(
        plan,
        command,
        cwd=cwd,
        env=env,
        active_child=execution_id,
        parent_span_id=parent_span_id,
        parent_run_id=parent_run_id,
    )
    return execution.exit_code, execution.timing
