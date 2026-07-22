"""Core datatypes for execution time control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    SUCCESS_SLOW = "success-slow"
    FAILED = "failed"
    TIMEOUT_STALL = "timeout-stall"
    TIMEOUT_HARD = "timeout-hard"
    INTERRUPTED = "interrupted"
    RUNNER_ERROR = "runner-error"
    BLOCKED_DUPLICATE = "blocked-duplicate"
    BLOCKED_ADMISSION = "blocked-admission"
    REUSED = "reused"


class AdmissionDecision(str, Enum):
    RUN = "run"
    REUSE = "reuse"
    NARROW = "narrow"
    DEFER_TO_PRE_FINAL = "defer-to-pre-final"
    REJECT_DUPLICATE = "reject-duplicate"
    BLOCK_CONTROLLER_ERROR = "block-controller-error"


@dataclass(frozen=True, slots=True)
class NormalizedContext:
    platform: str
    python_version: str
    execution_mode: str
    workload_bucket: str
    coverage: bool = False
    tui: bool = False
    packaging: bool = False
    environment: str = "unknown"
    test_file_count: int = 0
    test_node_count: int = 0

    def signature(self) -> str:
        parts = (
            self.platform,
            self.python_version,
            self.execution_mode,
            self.workload_bucket,
            "cov1" if self.coverage else "cov0",
            "tui1" if self.tui else "tui0",
            "pkg1" if self.packaging else "pkg0",
            self.environment,
        )
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    run_id: str
    execution_id: str
    profile_id: str
    normalized_signature: str
    workload_fingerprint: str
    policy_fingerprint: str
    expected_seconds: float
    soft_seconds: float
    stall_seconds: float | None
    hard_seconds: float
    diagnostic_hard_seconds: float
    termination_grace_seconds: float
    progress_contract_id: str | None
    termination_policy_id: str
    prediction_source: str
    confidence: str
    sample_count: int
    admission_decision: str
    context_signature: str
    child_plan_digest: str | None = None
    planned_child_count: int = 0
    planned_expected_sum: float = 0.0
    planned_soft_sum: float = 0.0
    orchestration_overhead_estimate: float = 0.0
    planned_child_expected_sum: float = 0.0
    planned_orchestration_overhead: float = 0.0

    def to_json_dict(self) -> dict[str, Any]:
        payload = {
            "runId": self.run_id,
            "executionId": self.execution_id,
            "profileId": self.profile_id,
            "normalizedSignature": self.normalized_signature,
            "workloadFingerprint": self.workload_fingerprint,
            "policyFingerprint": self.policy_fingerprint,
            "expectedSeconds": self.expected_seconds,
            "softSeconds": self.soft_seconds,
            "stallSeconds": self.stall_seconds,
            "hardSeconds": self.hard_seconds,
            "diagnosticHardSeconds": self.diagnostic_hard_seconds,
            "terminationGraceSeconds": self.termination_grace_seconds,
            "progressContractId": self.progress_contract_id,
            "terminationPolicyId": self.termination_policy_id,
            "predictionSource": self.prediction_source,
            "confidence": self.confidence,
            "sampleCount": self.sample_count,
            "admissionDecision": self.admission_decision,
            "contextSignature": self.context_signature,
        }
        if self.child_plan_digest is not None:
            payload["childPlanDigest"] = self.child_plan_digest
        if self.planned_child_count:
            payload["plannedChildCount"] = self.planned_child_count
        if self.planned_expected_sum:
            payload["plannedExpectedSum"] = self.planned_expected_sum
        if self.planned_soft_sum:
            payload["plannedSoftSum"] = self.planned_soft_sum
        if self.orchestration_overhead_estimate:
            payload["orchestrationOverheadEstimate"] = self.orchestration_overhead_estimate
        if self.planned_child_expected_sum:
            payload["plannedChildExpectedSum"] = self.planned_child_expected_sum
        if self.planned_orchestration_overhead:
            payload["plannedOrchestrationOverhead"] = self.planned_orchestration_overhead
        return payload


@dataclass(frozen=True, slots=True)
class SpanRecord:
    run_id: str
    span_id: str
    parent_span_id: str | None
    execution_id: str
    profile_id: str
    normalized_signature: str
    workload_fingerprint: str
    policy_fingerprint: str
    start_time: str
    end_time: str
    duration_seconds: float
    exit_code: int | None
    status: str
    expected_seconds: float
    soft_seconds: float
    stall_seconds: float | None
    hard_seconds: float
    prediction_source: str
    confidence: str
    sample_count: int
    progress_event_count: int
    maximum_progress_gap: float
    active_child_at_end: str | None
    accepted_for_learning: bool
    quarantine_reason: str | None
    diagnostic_bundle: str | None
