"""Timeout diagnostic bundles."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable

from .models import ExecutionPlan
from .paths import timeout_bundle_dir
from .process_tree import ProcessResult


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


def _run_bounded(
    *,
    deadline: float,
    failures: list[str],
    name: str,
    collector: Callable[[], Any],
    fraction: float = 0.25,
) -> Any:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        failures.append(f"{name}:budget-exhausted")
        return None
    budget = max(0.01, remaining * fraction)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(collector)
        try:
            return future.result(timeout=budget)
        except FuturesTimeout:
            failures.append(f"{name}:timeout")
            return None
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}:{type(exc).__name__}")
            return None


def _owned_process_snapshot(result: ProcessResult) -> dict[str, Any]:
    payload: dict[str, Any] = {"ownedPgid": result.owned_pgid}
    if result.owned_pgid is None:
        return payload
    try:
        os.kill(result.owned_pgid, 0)
        payload["ownedAlive"] = True
    except ProcessLookupError:
        payload["ownedAlive"] = False
    except PermissionError:
        payload["ownedAlive"] = True
    return payload


def collect_timeout_bundle(
    *,
    plan: ExecutionPlan,
    result: ProcessResult,
    active_child: str | None,
    timeout_kind: str,
    progress_timeline: list[dict[str, object]] | None = None,
) -> str:
    bundle_dir = timeout_bundle_dir(plan.run_id)
    deadline = time.monotonic() + plan.diagnostic_hard_seconds
    failures: list[str] = []

    owned_snapshot = _run_bounded(
        deadline=deadline,
        failures=failures,
        name="owned-process-group",
        collector=lambda: _owned_process_snapshot(result),
    )
    bounded_output = _run_bounded(
        deadline=deadline,
        failures=failures,
        name="bounded-output",
        collector=lambda: {
            "stdoutTail": _redact(result.stdout_tail),
            "stderrTail": _redact(result.stderr_tail),
        },
    )
    payload = {
        "schemaVersion": 1,
        "runId": plan.run_id,
        "executionId": plan.execution_id,
        "activeChildId": active_child,
        "timeoutKind": timeout_kind,
        "plan": plan.to_json_dict(),
        "ownedProcessGroup": owned_snapshot or {},
        "knownChildPids": [],
        "survivingOwnedPids": [],
        "boundedOutput": bounded_output or {},
        "progressTimeline": progress_timeline or [],
        "progressEventCount": result.progress_event_count,
        "maximumProgressGap": result.maximum_progress_gap,
        "recommendedDiagnostic": "python3 -m pytest <target> -vv --durations=20",
        "collectorFailures": failures,
        "diagnosticBudgetSeconds": plan.diagnostic_hard_seconds,
    }
    if time.monotonic() > deadline:
        failures.append("bundle-write:budget-exhausted")
        payload["collectorFailures"] = failures

    def _write_bundle() -> None:
        path = bundle_dir / "bundle.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _run_bounded(
        deadline=deadline,
        failures=failures,
        name="bundle-write",
        collector=_write_bundle,
        fraction=0.5,
    )
    payload["collectorFailures"] = failures
    path = bundle_dir / "bundle.json"
    if not path.is_file():
        bundle_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)
