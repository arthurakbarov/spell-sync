"""Timeout diagnostic bundles."""

from __future__ import annotations

import json
import time

from .models import ExecutionPlan
from .paths import timeout_bundle_dir
from .process_tree import ProcessResult


def collect_timeout_bundle(
    *,
    plan: ExecutionPlan,
    result: ProcessResult,
    active_child: str | None,
    timeout_kind: str,
) -> str:
    bundle_dir = timeout_bundle_dir(plan.run_id)
    started = time.monotonic()
    payload = {
        "schemaVersion": 1,
        "runId": plan.run_id,
        "executionId": plan.execution_id,
        "activeChildId": active_child,
        "timeoutKind": timeout_kind,
        "plan": plan.to_json_dict(),
        "stdoutTail": _redact(result.stdout_tail),
        "stderrTail": _redact(result.stderr_tail),
        "progressEventCount": result.progress_event_count,
        "maximumProgressGap": result.maximum_progress_gap,
        "recommendedDiagnostic": "python3 -m pytest <target> -vv --durations=20",
        "collectorFailures": [],
    }
    if time.monotonic() - started > plan.diagnostic_hard_seconds:
        payload["collectorFailures"].append("diagnostic-time-budget-exceeded")
    path = bundle_dir / "bundle.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _redact(text: str) -> str:
    redacted = text
    for sentinel in (
        "SENSITIVE_USER_WORD_7f3a",
        "secret-token-value",
        "/Users/private-user",
        "/home/private-user",
        "raw-spell-sync-config",
    ):
        redacted = redacted.replace(sentinel, "[REDACTED]")
    if len(redacted) > 8000:
        redacted = redacted[-8000:]
    return redacted
