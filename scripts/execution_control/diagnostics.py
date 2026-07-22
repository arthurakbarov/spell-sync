"""Timeout diagnostic bundles with bounded subprocess collectors."""

from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path
from typing import Any

from .models import ExecutionPlan
from .paths import timeout_bundle_dir
from .privacy import sanitize_text, workspace_roots
from .process_tree import ProcessResult, collect_descendants


def _collector_worker(name: str, payload: dict[str, Any], queue: multiprocessing.Queue) -> None:
    try:
        if name == "owned-process-group":
            root_pid = payload.get("ownedRootPid")
            pgid = payload.get("ownedPgid")
            result: dict[str, Any] = {"ownedPgid": pgid, "ownedRootPid": root_pid}
            if root_pid:
                result["descendantPids"] = sorted(collect_descendants(int(root_pid)))
            queue.put(("ok", result))
        elif name == "bundle-write":
            path = Path(str(payload["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload["body"], indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            queue.put(("ok", {"written": True, "path": str(path)}))
        elif name == "slow-sleep":
            time.sleep(float(payload.get("seconds", 0.25)))
            queue.put(("ok", {"slow": True}))
        else:
            queue.put(("ok", payload))
    except Exception as exc:  # noqa: BLE001
        queue.put(("error", f"{type(exc).__name__}"))


def _run_collector_process(
    *,
    name: str,
    payload: dict[str, Any],
    budget_seconds: float,
    failures: list[str],
) -> Any:
    if budget_seconds <= 0:
        failures.append(f"{name}:budget-exhausted")
        return None
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(target=_collector_worker, args=(name, payload, queue), daemon=True)
    proc.start()
    proc.join(timeout=budget_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(0.05)
        if proc.is_alive():
            proc.kill()
            proc.join(0.05)
        failures.append(f"{name}:timeout")
        return None
    if queue.empty():
        failures.append(f"{name}:empty-result")
        return None
    status, value = queue.get_nowait()
    if status != "ok":
        failures.append(f"{name}:{value}")
        return None
    return value


def _owned_process_snapshot(result: ProcessResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ownedPgid": result.owned_pgid,
        "ownedRootPid": result.owned_root_pid,
        "survivingOwnedPids": list(result.detached_pids),
    }
    if result.owned_root_pid is not None:
        payload["descendantPids"] = sorted(collect_descendants(result.owned_root_pid))
    return payload


def collect_timeout_bundle(
    *,
    plan: ExecutionPlan,
    result: ProcessResult,
    active_child: str | None,
    timeout_kind: str,
    progress_timeline: list[dict[str, object]] | None = None,
    public_root: Path | None = None,
) -> str:
    started = time.monotonic()
    deadline = started + plan.diagnostic_hard_seconds
    failures: list[str] = []
    roots = workspace_roots(public_root=public_root) if public_root is not None else ()

    owned_snapshot = _run_collector_process(
        name="owned-process-group",
        payload={
            "ownedPgid": result.owned_pgid,
            "ownedRootPid": result.owned_root_pid,
        },
        budget_seconds=max(0.0, deadline - time.monotonic()) * 0.4,
        failures=failures,
    )
    if owned_snapshot is None:
        owned_snapshot = _owned_process_snapshot(result)

    bounded_output = {
        "stdoutTail": sanitize_text(result.stdout_tail, workspace_roots=roots),
        "stderrTail": sanitize_text(result.stderr_tail, workspace_roots=roots),
    }

    payload = {
        "schemaVersion": 2,
        "runId": plan.run_id,
        "executionId": plan.execution_id,
        "activeChildId": active_child,
        "timeoutKind": timeout_kind,
        "plan": plan.to_json_dict(),
        "ownedProcessGroup": owned_snapshot or {},
        "knownChildPids": list(result.detached_pids),
        "survivingOwnedPids": list(result.detached_pids),
        "boundedOutput": bounded_output,
        "progressTimeline": progress_timeline or [],
        "progressEventCount": result.progress_event_count,
        "maximumProgressGap": result.maximum_progress_gap,
        "recommendedDiagnostic": "python3 -m pytest <target> -vv --durations=20",
        "collectorFailures": failures,
        "diagnosticBudgetSeconds": plan.diagnostic_hard_seconds,
        "elapsedSeconds": 0.0,
    }

    bundle_path = timeout_bundle_dir(plan.run_id) / "bundle.json"
    path: str | None = None
    remaining = max(0.0, deadline - time.monotonic())
    if remaining > 0:
        write_result = _run_collector_process(
            name="bundle-write",
            payload={"path": str(bundle_path), "body": payload},
            budget_seconds=remaining,
            failures=failures,
        )
        if isinstance(write_result, dict):
            path = str(write_result.get("path", bundle_path))

    payload["collectorFailures"] = failures
    payload["elapsedSeconds"] = round(time.monotonic() - started, 3)
    if path is None:
        try:
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            bundle_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            path = str(bundle_path)
        except OSError:
            failures.append("bundle-write:OSError")
            path = str(bundle_path)
    return path


def _redact(text: str, *, public_root: Path | None = None) -> str:
    roots = workspace_roots(public_root=public_root) if public_root is not None else ()
    return sanitize_text(text, workspace_roots=roots)
