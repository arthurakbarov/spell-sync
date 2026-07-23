"""Build execution budget reports from history and session state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .history import HistoryStore
from .registry import ExecutionBudgetRegistry, load_registry, REGISTRY_REL_PATH
from .session import build_edit_loop_summary, load_session
from .statistics import compute_mae, compute_mape, compute_stats, confidence_label

REPORT_SCHEMA_VERSION = 1
MINIMUM_SAMPLES_FOR_ACCURACY = 5


@dataclass(frozen=True, slots=True)
class ExecutionIdStats:
    execution_id: str
    sample_count: int
    success_count: int
    failure_count: int
    timeout_count: int
    interrupt_count: int
    slow_success_count: int
    median_actual_seconds: float
    p90_actual_seconds: float
    p95_actual_seconds: float | None
    last_expected_seconds: float | None
    last_actual_seconds: float | None
    mean_absolute_error_seconds: float | None
    mean_absolute_percentage_error: float | None
    run_decision_count: int
    reuse_decision_count: int
    narrow_decision_count: int
    defer_decision_count: int
    actual_seconds_total: float
    estimated_seconds_avoided_by_reuse: float
    maximum_progress_gap_seconds: float
    confidence: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "sampleCount": self.sample_count,
            "successCount": self.success_count,
            "failureCount": self.failure_count,
            "timeoutCount": self.timeout_count,
            "interruptCount": self.interrupt_count,
            "slowSuccessCount": self.slow_success_count,
            "medianActualSeconds": self.median_actual_seconds,
            "p90ActualSeconds": self.p90_actual_seconds,
            "p95ActualSeconds": self.p95_actual_seconds,
            "lastExpectedSeconds": self.last_expected_seconds,
            "lastActualSeconds": self.last_actual_seconds,
            "meanAbsoluteErrorSeconds": self.mean_absolute_error_seconds,
            "meanAbsolutePercentageError": self.mean_absolute_percentage_error,
            "runDecisionCount": self.run_decision_count,
            "reuseDecisionCount": self.reuse_decision_count,
            "narrowDecisionCount": self.narrow_decision_count,
            "deferDecisionCount": self.defer_decision_count,
            "actualSecondsTotal": round(self.actual_seconds_total, 2),
            "estimatedSecondsAvoidedByReuse": round(self.estimated_seconds_avoided_by_reuse, 2),
            "maximumProgressGapSeconds": self.maximum_progress_gap_seconds,
            "confidence": self.confidence,
        }


def _parse_window(window: str | None) -> datetime | None:
    if not window:
        return None
    if window.endswith("d"):
        days = int(window[:-1])
        return datetime.now(timezone.utc) - timedelta(days=days)
    return None


def build_execution_budget_report(
    root: Path,
    *,
    history: HistoryStore | None = None,
    registry: ExecutionBudgetRegistry | None = None,
    execution_id: str | None = None,
    window: str | None = None,
    edit_loop: bool = False,
) -> dict[str, Any]:
    registry = registry or load_registry(root / REGISTRY_REL_PATH)
    history = history or HistoryStore.open()
    since = _parse_window(window)
    rows = history.fetch_report_spans(
        execution_id=execution_id,
        since=since,
    )
    execution_ids = sorted({str(row["execution_id"]) for row in rows})
    if execution_id:
        execution_ids = [execution_id]

    by_execution: dict[str, list[dict[str, Any]]] = {item: [] for item in execution_ids}
    for row in rows:
        by_execution.setdefault(str(row["execution_id"]), []).append(row)

    stats: list[ExecutionIdStats] = []
    for item in execution_ids:
        stats.append(_stats_for_execution(item, by_execution.get(item, [])))

    session_totals, _, _ = load_session()
    edit_loop_summary = build_edit_loop_summary(session_totals, history=history)
    cohort = _environment_cohort(rows)

    payload: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "historyHealth": "degraded" if history.degraded else "healthy",
        "historyPath": str(history.path),
        "sampleWindow": window or "all",
        "environmentCohort": cohort,
        "globalHardCapSeconds": registry.global_hard_cap_seconds,
        "executionIds": [item.to_json_dict() for item in stats],
    }
    if edit_loop or not execution_id:
        payload["editLoopSummary"] = edit_loop_summary
    return payload


def _environment_cohort(rows: list[dict[str, Any]]) -> str:
    signatures = sorted({str(row.get("environment_signature") or "") for row in rows if row})
    signatures = [item for item in signatures if item]
    if not signatures:
        return "unknown"
    if len(signatures) == 1:
        return signatures[0][:16]
    return "mixed"

def _stats_for_execution(execution_id: str, rows: list[dict[str, Any]]) -> ExecutionIdStats:
    durations = [float(row["duration_seconds"]) for row in rows]
    stats = compute_stats(durations, progress_gaps=[float(row["maximum_progress_gap"]) for row in rows])
    success = sum(1 for row in rows if row["status"] in {"success", "success-slow"})
    failure = sum(1 for row in rows if row["status"] == "failed")
    timeout = sum(1 for row in rows if row["status"] in {"timeout-hard", "timeout-stall"})
    interrupt = sum(1 for row in rows if row["status"] == "interrupted")
    slow_success = sum(1 for row in rows if row["status"] == "success-slow")
    expected = [float(row["expected_seconds"]) for row in rows]
    actual = durations
    mae = compute_mae(expected, actual) if len(rows) >= MINIMUM_SAMPLES_FOR_ACCURACY else None
    mape = compute_mape(expected, actual) if len(rows) >= MINIMUM_SAMPLES_FOR_ACCURACY else None
    confidence = confidence_label(stats.sample_count)
    if stats.sample_count < MINIMUM_SAMPLES_FOR_ACCURACY:
        confidence = "insufficient-data"
    last_expected = float(rows[0]["expected_seconds"]) if rows else None
    last_actual = float(rows[0]["duration_seconds"]) if rows else None
    admission = _admission_counts(rows)
    reuse_avoided = sum(
        float(row["expected_seconds"])
        for row in rows
        if row["status"] == "reused"
    )
    return ExecutionIdStats(
        execution_id=execution_id,
        sample_count=stats.sample_count,
        success_count=success,
        failure_count=failure,
        timeout_count=timeout,
        interrupt_count=interrupt,
        slow_success_count=slow_success,
        median_actual_seconds=round(stats.median, 2),
        p90_actual_seconds=round(stats.p90, 2),
        p95_actual_seconds=round(stats.p95, 2) if stats.p95 is not None else None,
        last_expected_seconds=round(last_expected, 2) if last_expected is not None else None,
        last_actual_seconds=round(last_actual, 2) if last_actual is not None else None,
        mean_absolute_error_seconds=round(mae, 2) if mae is not None else None,
        mean_absolute_percentage_error=round(mape, 4) if mape is not None else None,
        run_decision_count=admission["run"],
        reuse_decision_count=admission["reuse"],
        narrow_decision_count=admission["narrow"],
        defer_decision_count=admission["defer"],
        actual_seconds_total=sum(durations),
        estimated_seconds_avoided_by_reuse=reuse_avoided,
        maximum_progress_gap_seconds=round(stats.max_progress_gap, 2),
        confidence=confidence,
    )


def _admission_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"run": 0, "reuse": 0, "narrow": 0, "defer": 0}
    for row in rows:
        status = str(row["status"])
        if status == "reused":
            counts["reuse"] += 1
        elif status == "blocked-admission":
            counts["defer"] += 1
        else:
            counts["run"] += 1
    return counts


def render_text_report(payload: dict[str, Any]) -> str:
    lines = [
        "EXECUTION_BUDGET_REPORT=success",
        f"EXECUTION_REPORT_SCHEMA_VERSION={payload['schemaVersion']}",
        f"EXECUTION_HISTORY_HEALTH={payload['historyHealth']}",
        f"EXECUTION_HISTORY_PATH={payload['historyPath']}",
        f"EXECUTION_SAMPLE_WINDOW={payload['sampleWindow']}",
        f"EXECUTION_ENVIRONMENT_COHORT={payload['environmentCohort']}",
    ]
    for item in payload.get("executionIds", []):
        lines.append(f"EXECUTION_ID={item['executionId']}")
        lines.append(f"EXECUTION_SAMPLE_COUNT={item['sampleCount']}")
        lines.append(f"EXECUTION_CONFIDENCE={item['confidence']}")
        lines.append(f"EXECUTION_MEDIAN_ACTUAL={item['medianActualSeconds']}")
        lines.append(f"EXECUTION_P90_ACTUAL={item['p90ActualSeconds']}")
        if item["meanAbsoluteErrorSeconds"] is not None:
            lines.append(f"EXECUTION_MAE_SECONDS={item['meanAbsoluteErrorSeconds']}")
        if item["meanAbsolutePercentageError"] is not None:
            lines.append(f"EXECUTION_MAPE={item['meanAbsolutePercentageError']}")
        lines.append(f"EXECUTION_REUSE_COUNT={item['reuseDecisionCount']}")
        lines.append(f"EXECUTION_SECONDS_AVOIDED={item['estimatedSecondsAvoidedByReuse']}")
    summary = payload.get("editLoopSummary")
    if isinstance(summary, dict):
        lines.append(f"EDIT_LOOP_SESSION_COUNT={summary.get('sessionCount', 0)}")
        lines.append(f"EDIT_LOOP_TEST_TIME_SHARE={summary.get('testTimeShare', 0)}")
        lines.append(f"EDIT_LOOP_ESTIMATED_SECONDS_AVOIDED={summary.get('estimatedSecondsAvoided', 0)}")
        lines.append(f"EDIT_LOOP_MEDIAN_FOCUSED_SECONDS={summary.get('medianFocusedCycleSeconds', 0)}")
    return "\n".join(lines) + "\n"


def write_privacy_safe_execution_summary(root: Path, payload: dict[str, Any]) -> Path:
    """Write aggregated, sanitized execution summary for snapshot retention."""
    edit_loop = payload.get("editLoopSummary")
    if not isinstance(edit_loop, dict):
        edit_loop = {}
    sanitized_ids = []
    for item in payload.get("executionIds", []):
        if not isinstance(item, dict):
            continue
        sanitized_ids.append(
            {
                "executionId": item.get("executionId"),
                "sampleCount": item.get("sampleCount"),
                "confidence": item.get("confidence"),
                "medianActualSeconds": item.get("medianActualSeconds"),
                "p90ActualSeconds": item.get("p90ActualSeconds"),
                "meanAbsoluteErrorSeconds": item.get("meanAbsoluteErrorSeconds"),
                "reuseDecisionCount": item.get("reuseDecisionCount"),
                "estimatedSecondsAvoidedByReuse": item.get("estimatedSecondsAvoidedByReuse"),
            }
        )
    summary = {
        "schemaVersion": 1,
        "generatedAt": payload.get("generatedAt"),
        "historyHealth": payload.get("historyHealth"),
        "sampleWindow": payload.get("sampleWindow"),
        "environmentCohort": payload.get("environmentCohort"),
        "editLoopSummary": edit_loop,
        "executionIds": sanitized_ids,
    }
    out = root / ".artifacts" / "execution" / "execution-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
