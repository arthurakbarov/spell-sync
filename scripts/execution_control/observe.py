"""Lightweight announce + measure + learn for commands outside hard budget control."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .eta import (
    DEFAULT_ANNOUNCE_THRESHOLD,
    announce_expected_eta,
    estimate_work_seconds,
    load_eta_config,
)
from .history import HistoryStore
from .interactive import (
    capture_waiting,
    current_waiting_seconds,
    interactive_allowance_seconds,
)
from .models import SpanRecord
from .session import record_session_event


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fingerprint(parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


@dataclass(frozen=True, slots=True)
class ObserveResult:
    exit_code: int
    work_seconds: float
    waiting_seconds: float
    wall_seconds: float
    learning_accepted: bool
    execution_id: str


def observe_subprocess(
    *,
    root: Path,
    execution_id: str,
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    prompt_count: int = 0,
    expected_hint: float | None = None,
    soft_multiplier: float = 2.0,
    profile_id: str = "observe",
    history: HistoryStore | None = None,
    announce: bool = True,
    print_result: bool = True,
) -> ObserveResult:
    """Run a subprocess with ETA announce and history learning (no hard kill)."""
    close = False
    store = history
    if store is None:
        store = HistoryStore.open()
        close = True
    try:
        cfg = load_eta_config(root=root)
        work, source, samples = estimate_work_seconds(
            execution_id,
            root=root,
            history=store,
            config=cfg,
            hint=expected_hint,
        )
        allowance = interactive_allowance_seconds(prompt_count)
        if announce:
            announce_expected_eta(
                execution_id,
                work_seconds=work,
                prompt_count=prompt_count,
                root=root,
                history=store,
                config=cfg,
                hint=expected_hint,
            )
        soft = max(work * soft_multiplier, work + 1.0)
        hard = soft * 2.0 + allowance
        start_iso = _utc_now()
        wall_started = time.monotonic()
        with capture_waiting():
            proc = subprocess.run(
                command,
                cwd=cwd or root,
                env=env,
                check=False,
            )
            waiting = current_waiting_seconds()
        wall = time.monotonic() - wall_started
        work_duration = max(0.0, wall - waiting)
        end_iso = _utc_now()
        exit_code = int(proc.returncode)
        accepted = exit_code == 0 and work_duration <= soft
        status = "success" if accepted else ("success-slow" if exit_code == 0 else "failed")
        quarantine = None if accepted else ("soft-overrun" if exit_code == 0 else None)
        sig = _fingerprint((execution_id, *command[:6]))
        record = SpanRecord(
            run_id=f"observe-{store.new_span_id()}",
            span_id=store.new_span_id(),
            parent_span_id=None,
            execution_id=execution_id,
            profile_id=profile_id,
            normalized_signature=sig,
            workload_fingerprint=sig,
            policy_fingerprint="observe-v1",
            start_time=start_iso,
            end_time=end_iso,
            duration_seconds=work_duration,
            exit_code=exit_code,
            status=status,
            expected_seconds=work,
            soft_seconds=soft,
            stall_seconds=None,
            hard_seconds=hard,
            prediction_source=source,
            confidence="history" if samples else "bootstrap",
            sample_count=samples,
            progress_event_count=0,
            maximum_progress_gap=0.0,
            active_child_at_end=execution_id,
            accepted_for_learning=accepted,
            quarantine_reason=quarantine,
            diagnostic_bundle=None,
        )
        store.insert_span(record, context_signature="observe")
        # Waiting is already session-recorded by prompt_user when used.
        record_session_event(category="focused", duration_seconds=work_duration)
        if print_result and os.environ.get("SPELL_SYNC_OBSERVE_PRINT", "1") != "0":
            print(f"OBSERVE_ID={execution_id}", flush=True)
            print(f"OBSERVE_EXIT={exit_code}", flush=True)
            print(f"OBSERVE_WORK_SECONDS={work_duration:.2f}", flush=True)
            print(f"OBSERVE_WAITING_SECONDS={waiting:.2f}", flush=True)
            print(f"OBSERVE_LEARNING_ACCEPTED={'true' if accepted else 'false'}", flush=True)
        return ObserveResult(
            exit_code=exit_code,
            work_seconds=work_duration,
            waiting_seconds=waiting,
            wall_seconds=wall,
            learning_accepted=accepted,
            execution_id=execution_id,
        )
    finally:
        if close and store is not None:
            store.close()


def record_observation(
    *,
    execution_id: str,
    duration_seconds: float,
    exit_code: int,
    expected_seconds: float,
    soft_seconds: float | None = None,
    profile_id: str = "observe",
    prediction_source: str = "hint",
    history: HistoryStore | None = None,
) -> bool:
    """Persist one measured sample so future ETA announcements can learn."""
    close = False
    store = history
    if store is None:
        store = HistoryStore.open()
        close = True
    try:
        soft = float(soft_seconds) if soft_seconds is not None else max(expected_seconds * 2.0, 1.0)
        accepted = exit_code == 0 and duration_seconds <= soft
        now = _utc_now()
        sig = _fingerprint((execution_id, prediction_source))
        store.insert_span(
            SpanRecord(
                run_id=f"observe-{store.new_span_id()}",
                span_id=store.new_span_id(),
                parent_span_id=None,
                execution_id=execution_id,
                profile_id=profile_id,
                normalized_signature=sig,
                workload_fingerprint=sig,
                policy_fingerprint="observe-v1",
                start_time=now,
                end_time=now,
                duration_seconds=float(duration_seconds),
                exit_code=int(exit_code),
                status="success" if accepted else ("success-slow" if exit_code == 0 else "failed"),
                expected_seconds=float(expected_seconds),
                soft_seconds=soft,
                stall_seconds=None,
                hard_seconds=soft * 2.0,
                prediction_source=prediction_source,
                confidence="bootstrap",
                sample_count=0,
                progress_event_count=0,
                maximum_progress_gap=0.0,
                active_child_at_end=execution_id,
                accepted_for_learning=accepted,
                quarantine_reason=None
                if accepted
                else ("soft-overrun" if exit_code == 0 else None),
                diagnostic_bundle=None,
            ),
            context_signature="observe",
        )
        return accepted
    finally:
        if close and store is not None:
            store.close()


def threshold_seconds(root: Path | None = None) -> float:
    cfg = load_eta_config(root=root)
    return float(cfg.get("announceThresholdSeconds", DEFAULT_ANNOUNCE_THRESHOLD))
