"""Local session cost accounting and warnings."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .paths import state_root


@dataclass(frozen=True, slots=True)
class SessionTotals:
    edit_seconds: float = 0.0
    focused_seconds: float = 0.0
    pre_final_seconds: float = 0.0
    full_ci_seconds: float = 0.0
    diagnostic_seconds: float = 0.0
    waiting_seconds: float = 0.0
    reused_seconds_saved: float = 0.0


def _session_path() -> Path:
    return state_root() / "session.json"


def load_session() -> tuple[SessionTotals, float, float]:
    path = _session_path()
    now = time.monotonic()
    if not path.is_file():
        return SessionTotals(), now, now
    payload = json.loads(path.read_text(encoding="utf-8"))
    totals = SessionTotals(
        edit_seconds=float(payload.get("editSeconds", 0)),
        focused_seconds=float(payload.get("focusedSeconds", 0)),
        pre_final_seconds=float(payload.get("preFinalSeconds", 0)),
        full_ci_seconds=float(payload.get("fullCiSeconds", 0)),
        diagnostic_seconds=float(payload.get("diagnosticSeconds", 0)),
        waiting_seconds=float(payload.get("waitingSeconds", 0)),
        reused_seconds_saved=float(payload.get("reusedSecondsSaved", 0)),
    )
    window_started = float(payload.get("windowStartedMonotonic", now))
    last_updated = float(payload.get("lastUpdatedMonotonic", window_started))
    return totals, window_started, last_updated


def current_session_test_share(*, window_seconds: float = 1800.0) -> float | None:
    totals, window_started, _last_updated = load_session()
    now = time.monotonic()
    if now - window_started > window_seconds:
        return None
    session_seconds = max(1.0, totals.edit_seconds)
    test_seconds = totals.focused_seconds + totals.pre_final_seconds + totals.full_ci_seconds
    if test_seconds <= 0:
        return None
    return test_seconds / session_seconds


def record_session_event(
    *,
    category: str,
    duration_seconds: float,
    reused_saved: float = 0.0,
    window_seconds: float = 1800.0,
    warn_share: float = 0.6,
) -> None:
    totals, window_started, last_updated = load_session()
    now = time.monotonic()
    if now - window_started > window_seconds:
        totals = SessionTotals()
        window_started = now
        last_updated = now
    edit_delta = max(0.0, now - last_updated)
    updated = SessionTotals(
        edit_seconds=totals.edit_seconds + edit_delta,
        focused_seconds=totals.focused_seconds
        + (duration_seconds if category == "focused" else 0.0),
        pre_final_seconds=totals.pre_final_seconds
        + (duration_seconds if category == "pre-final" else 0.0),
        full_ci_seconds=totals.full_ci_seconds
        + (duration_seconds if category == "full-ci" else 0.0),
        diagnostic_seconds=totals.diagnostic_seconds
        + (duration_seconds if category == "diagnostic" else 0.0),
        waiting_seconds=totals.waiting_seconds
        + (duration_seconds if category == "waiting" else 0.0),
        reused_seconds_saved=totals.reused_seconds_saved + reused_saved,
    )
    session_seconds = max(1.0, updated.edit_seconds)
    test_seconds = (
        updated.focused_seconds
        + updated.pre_final_seconds
        + updated.full_ci_seconds
        + updated.diagnostic_seconds
    )
    payload = {
        "editSeconds": updated.edit_seconds,
        "focusedSeconds": updated.focused_seconds,
        "preFinalSeconds": updated.pre_final_seconds,
        "fullCiSeconds": updated.full_ci_seconds,
        "diagnosticSeconds": updated.diagnostic_seconds,
        "waitingSeconds": updated.waiting_seconds,
        "reusedSecondsSaved": updated.reused_seconds_saved,
        "windowStartedMonotonic": window_started,
        "lastUpdatedMonotonic": now,
    }
    _session_path().write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if test_seconds / session_seconds > warn_share:
        print("EXECUTION_WARNING=test-time-dominates-edit-loop")
        print(f"EXECUTION_SESSION_TEST_SECONDS={test_seconds:.0f}")
        print(f"EXECUTION_SESSION_EDIT_SECONDS={session_seconds:.0f}")


def check_performance_regression(
    *,
    execution_id: str,
    workload_fingerprint: str,
    old_median: float,
    new_median: float,
    old_count: int,
    new_count: int,
    threshold: float = 0.25,
) -> None:
    if old_median <= 0 or new_median <= old_median:
        return
    delta = (new_median - old_median) / old_median
    if delta < threshold:
        return
    print("EXECUTION_WARNING=performance-regression-candidate")
    print(f"EXECUTION_REGRESSION_ID={execution_id}")
    print(f"EXECUTION_REGRESSION_WORKLOAD={workload_fingerprint[:16]}")
    print(f"EXECUTION_REGRESSION_OLD_MEDIAN={old_median:.2f}")
    print(f"EXECUTION_REGRESSION_NEW_MEDIAN={new_median:.2f}")
    print(f"EXECUTION_REGRESSION_DELTA={delta:.2%}")
    print(f"EXECUTION_REGRESSION_OLD_COUNT={old_count}")
    print(f"EXECUTION_REGRESSION_NEW_COUNT={new_count}")
