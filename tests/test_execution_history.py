"""SQLite execution history tests."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone

from scripts.execution_control.history import HistoryStore
from scripts.execution_control.models import SpanRecord
from scripts.execution_control.paths import history_database_path
from tests.conftest_execution import sqlite_preflight_probe


def _span(**overrides) -> SpanRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    base = dict(
        run_id="run-history",
        span_id="span-1",
        parent_span_id=None,
        execution_id="ci:pytest",
        profile_id="ci-child",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        start_time=now,
        end_time=now,
        duration_seconds=1.0,
        exit_code=0,
        status="success",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        progress_event_count=1,
        maximum_progress_gap=0.1,
        active_child_at_end="ci:pytest",
        accepted_for_learning=True,
        quarantine_reason=None,
        diagnostic_bundle=None,
    )
    base.update(overrides)
    return SpanRecord(**base)


def test_sqlite_preflight_wal_outside_repo(isolated_state_dir):
    db = isolated_state_dir / "spell-sync" / "execution-control" / "probe.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    sqlite_preflight_probe(db)


def test_history_uses_wal_mode(isolated_state_dir, history):
    del isolated_state_dir
    connection = sqlite3.connect(history.path)
    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    connection.close()
    assert mode.lower() == "wal"


def test_history_persists_span(isolated_state_dir, history):
    del isolated_state_dir
    history.insert_span(_span(), context_signature="ctx")
    rows = history.fetch_learning_durations(
        execution_id="ci:pytest",
        workload_fingerprint="wf",
    )
    assert rows == [1.0]


def test_corruption_quarantine(isolated_state_dir):
    store = HistoryStore.open()
    store._initialize()
    path = history_database_path()
    for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if candidate.exists():
            candidate.write_bytes(b"not-a-database")
    recovered = HistoryStore.open()
    assert recovered.degraded is True
    recovered.insert_span(
        _span(run_id="after-quarantine", span_id="span-after"), context_signature="ctx"
    )
    rows = recovered.fetch_learning_durations(
        execution_id="ci:pytest",
        workload_fingerprint="wf",
    )
    assert rows == [1.0]


def test_retention_caps_at_500(isolated_state_dir, history):
    del isolated_state_dir
    for index in range(505):
        history.insert_span(
            _span(run_id=f"run-{index}", span_id=f"span-{index}"),
            context_signature="ctx",
        )
    with history._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM spans WHERE execution_id = ?",
            ("ci:pytest",),
        ).fetchone()[0]
    assert count == 500


def test_concurrent_writers(isolated_state_dir, history):
    del isolated_state_dir

    def writer(index: int) -> None:
        store = HistoryStore.open()
        store.insert_span(
            _span(run_id=f"c-{index}", span_id=f"c-span-{index}"),
            context_signature="ctx",
        )

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    with history._connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
    assert count >= 8


def test_acquire_lease_and_release(isolated_state_dir, history):
    del isolated_state_dir
    signature = "lease-signature" * 2
    acquired, owner = history.acquire_lease(
        normalized_signature=signature,
        run_id="run-lease-1",
        execution_id="gate:focused-module",
        owner_pid=os.getpid(),
    )
    assert acquired is True
    assert owner is None
    duplicate, existing = history.acquire_lease(
        normalized_signature=signature,
        run_id="run-lease-2",
        execution_id="gate:focused-module",
        owner_pid=os.getpid(),
    )
    assert duplicate is False
    assert existing is not None
    history.release_lease(signature)
    reacquired, _ = history.acquire_lease(
        normalized_signature=signature,
        run_id="run-lease-3",
        execution_id="gate:focused-module",
        owner_pid=os.getpid(),
    )
    assert reacquired is True


def test_stale_lease_from_dead_pid(isolated_state_dir, history):
    del isolated_state_dir
    signature = "stale-lease-sig" * 2
    acquired, _ = history.acquire_lease(
        normalized_signature=signature,
        run_id="run-stale",
        execution_id="gate:focused-module",
        owner_pid=999999,
    )
    assert acquired is True
    reacquired, owner = history.acquire_lease(
        normalized_signature=signature,
        run_id="run-new",
        execution_id="gate:focused-module",
        owner_pid=os.getpid(),
    )
    assert reacquired is True
    assert owner is None


def test_admin_accept_slow_sample(isolated_state_dir, history):
    del isolated_state_dir
    history.insert_span(
        _span(status="success-slow", accepted_for_learning=False, quarantine_reason="soft-overrun"),
        context_signature="ctx",
    )
    assert history.accept_sample("run-history", "manual review") is True
    with history._connect() as connection:
        row = connection.execute(
            "SELECT accepted_for_learning, quarantine_reason FROM spans WHERE run_id = ?",
            ("run-history",),
        ).fetchone()
    assert row["accepted_for_learning"] == 1
    assert row["quarantine_reason"] is None


def test_admin_reject_sample(isolated_state_dir, history):
    del isolated_state_dir
    history.insert_span(_span(), context_signature="ctx")
    assert history.reject_sample("run-history", "noisy-run") is True
    with history._connect() as connection:
        row = connection.execute(
            "SELECT accepted_for_learning, quarantine_reason FROM spans WHERE run_id = ?",
            ("run-history",),
        ).fetchone()
    assert row["accepted_for_learning"] == 0
    assert row["quarantine_reason"] == "rejected:noisy-run"
