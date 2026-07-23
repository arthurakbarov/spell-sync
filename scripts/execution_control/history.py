"""Persistent SQLite execution history."""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import SpanRecord
from .paths import HISTORY_SCHEMA_VERSION, history_database_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
    run_id TEXT NOT NULL,
    span_id TEXT PRIMARY KEY,
    parent_span_id TEXT,
    execution_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    normalized_signature TEXT NOT NULL,
    workload_fingerprint TEXT NOT NULL,
    policy_fingerprint TEXT NOT NULL,
    context_signature TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    exit_code INTEGER,
    status TEXT NOT NULL,
    expected_seconds REAL NOT NULL,
    soft_seconds REAL NOT NULL,
    stall_seconds REAL,
    hard_seconds REAL NOT NULL,
    prediction_source TEXT NOT NULL,
    confidence TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    progress_event_count INTEGER NOT NULL,
    maximum_progress_gap REAL NOT NULL,
    active_child_at_end TEXT,
    accepted_for_learning INTEGER NOT NULL,
    quarantine_reason TEXT,
    diagnostic_bundle TEXT
);

CREATE TABLE IF NOT EXISTS active_leases (
    normalized_signature TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    owner_pid INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    active_child TEXT
);

CREATE TABLE IF NOT EXISTS admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    run_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_spans_execution ON spans(execution_id);
CREATE INDEX IF NOT EXISTS idx_spans_signature ON spans(normalized_signature);
CREATE INDEX IF NOT EXISTS idx_spans_status ON spans(status);
CREATE INDEX IF NOT EXISTS idx_spans_run_id ON spans(run_id);
"""


@dataclass
class HistoryStore:
    path: Path
    degraded: bool = False
    _held_connection: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    def close(self) -> None:
        if self._held_connection is not None:
            self._held_connection.close()
            self._held_connection = None

    def __enter__(self) -> HistoryStore:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @classmethod
    def open(cls, path: Path | None = None) -> HistoryStore:
        db_path = path or history_database_path()
        store = cls(path=db_path)
        try:
            store._initialize()
            with store._connect() as connection:
                connection.execute("SELECT 1 FROM schema_meta LIMIT 1").fetchone()
        except sqlite3.DatabaseError:
            store._quarantine_and_recreate()
        return store

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(spans)").fetchall()}
            if "environment_signature" not in columns:
                connection.execute(
                    "ALTER TABLE spans ADD COLUMN environment_signature TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("schemaVersion", str(HISTORY_SCHEMA_VERSION)),
            )
            connection.commit()

    def _quarantine_and_recreate(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if self.path.exists():
            shutil.move(str(self.path), str(self.path.with_suffix(f".quarantine-{stamp}.sqlite3")))
        self.degraded = True
        self._initialize()

    def insert_span(self, record: SpanRecord, *, context_signature: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO spans (
                        run_id, span_id, parent_span_id, execution_id, profile_id,
                        normalized_signature, workload_fingerprint, policy_fingerprint,
                        context_signature, environment_signature, start_time, end_time,
                        duration_seconds,
                        exit_code, status, expected_seconds, soft_seconds, stall_seconds,
                        hard_seconds, prediction_source, confidence, sample_count,
                        progress_event_count, maximum_progress_gap, active_child_at_end,
                        accepted_for_learning, quarantine_reason, diagnostic_bundle
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        record.run_id,
                        record.span_id,
                        record.parent_span_id,
                        record.execution_id,
                        record.profile_id,
                        record.normalized_signature,
                        record.workload_fingerprint,
                        record.policy_fingerprint,
                        context_signature,
                        record.environment_signature,
                        record.start_time,
                        record.end_time,
                        record.duration_seconds,
                        record.exit_code,
                        record.status,
                        record.expected_seconds,
                        record.soft_seconds,
                        record.stall_seconds,
                        record.hard_seconds,
                        record.prediction_source,
                        record.confidence,
                        record.sample_count,
                        record.progress_event_count,
                        record.maximum_progress_gap,
                        record.active_child_at_end,
                        1 if record.accepted_for_learning else 0,
                        record.quarantine_reason,
                        record.diagnostic_bundle,
                    ),
                )
                self._enforce_retention(connection, record.execution_id)
                connection.commit()
        except sqlite3.Error:
            self.degraded = True

    def _enforce_retention(self, connection: sqlite3.Connection, execution_id: str) -> None:
        rows = connection.execute(
            """
            SELECT span_id FROM spans
            WHERE execution_id = ?
            ORDER BY start_time DESC
            """,
            (execution_id,),
        ).fetchall()
        if len(rows) <= 500:
            return
        drop_ids = [row["span_id"] for row in rows[500:]]
        connection.executemany(
            "DELETE FROM spans WHERE span_id = ?", ((item,) for item in drop_ids)
        )

    def fetch_learning_durations(
        self,
        *,
        execution_id: str,
        workload_fingerprint: str,
        context_signature: str | None = None,
        limit: int = 30,
    ) -> list[float]:
        query = """
            SELECT duration_seconds FROM spans
            WHERE execution_id = ?
              AND workload_fingerprint = ?
              AND accepted_for_learning = 1
              AND status = 'success'
        """
        params: list[object] = [execution_id, workload_fingerprint]
        if context_signature is not None:
            query += " AND context_signature = ?"
            params.append(context_signature)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        try:
            with self._connect() as connection:
                rows = connection.execute(query, params).fetchall()
        except sqlite3.Error:
            self.degraded = True
            return []
        return [float(row["duration_seconds"]) for row in rows]

    def fetch_profile_durations(self, *, execution_id: str, limit: int = 30) -> list[float]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT duration_seconds FROM spans
                    WHERE execution_id = ?
                      AND accepted_for_learning = 1
                      AND status = 'success'
                    ORDER BY start_time DESC LIMIT ?
                    """,
                    (execution_id, limit),
                ).fetchall()
        except sqlite3.Error:
            self.degraded = True
            return []
        return [float(row["duration_seconds"]) for row in rows]

    def fetch_report_spans(
        self,
        *,
        execution_id: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[dict[str, object]]:
        query = """
            SELECT execution_id, duration_seconds, expected_seconds, status,
                   maximum_progress_gap, environment_signature, start_time
            FROM spans
            WHERE 1=1
        """
        params: list[object] = []
        if execution_id:
            query += " AND execution_id = ?"
            params.append(execution_id)
        if since is not None:
            query += " AND start_time >= ?"
            params.append(since.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        try:
            with self._connect() as connection:
                rows = connection.execute(query, params).fetchall()
        except sqlite3.Error:
            self.degraded = True
            return []
        return [dict(row) for row in rows]

    def fetch_parent_overhead_samples(
        self,
        *,
        execution_id: str,
        limit: int = 30,
    ) -> list[float]:
        try:
            with self._connect() as connection:
                parents = connection.execute(
                    """
                    SELECT run_id, duration_seconds FROM spans
                    WHERE execution_id = ?
                      AND parent_span_id IS NULL
                      AND accepted_for_learning = 1
                      AND status IN ('success', 'success-slow')
                    ORDER BY start_time DESC LIMIT ?
                    """,
                    (execution_id, limit),
                ).fetchall()
                samples: list[float] = []
                for parent in parents:
                    child_sum = connection.execute(
                        """
                        SELECT COALESCE(SUM(duration_seconds), 0) AS total
                        FROM spans
                        WHERE run_id = ? AND parent_span_id IS NOT NULL
                        """,
                        (parent["run_id"],),
                    ).fetchone()
                    child_total = float(child_sum["total"]) if child_sum else 0.0
                    samples.append(max(0.0, float(parent["duration_seconds"]) - child_total))
        except sqlite3.Error:
            self.degraded = True
            return []
        return samples

    def count_gate_runs(self, execution_id: str) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS total FROM spans
                    WHERE execution_id = ? AND parent_span_id IS NULL
                    """,
                    (execution_id,),
                ).fetchone()
        except sqlite3.Error:
            self.degraded = True
            return 0
        return int(row["total"]) if row else 0

    def acquire_lease(
        self,
        *,
        normalized_signature: str,
        run_id: str,
        execution_id: str,
        owner_pid: int,
        active_child: str | None = None,
    ) -> tuple[bool, dict[str, object] | None]:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM active_leases WHERE normalized_signature = ?",
                    (normalized_signature,),
                ).fetchone()
                if existing is not None:
                    owner_pid = int(existing["owner_pid"])
                    if self._pid_alive(owner_pid):
                        connection.execute("ROLLBACK")
                        return False, dict(existing)
                    connection.execute(
                        "DELETE FROM active_leases WHERE normalized_signature = ?",
                        (normalized_signature,),
                    )
                connection.execute(
                    """
                    INSERT INTO active_leases(
                        normalized_signature,
                        run_id,
                        execution_id,
                        owner_pid,
                        started_at,
                        active_child
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (normalized_signature, run_id, execution_id, owner_pid, now, active_child),
                )
                connection.commit()
                return True, None
        except sqlite3.Error:
            self.degraded = True
            return True, None

    def release_lease(self, normalized_signature: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM active_leases WHERE normalized_signature = ?",
                    (normalized_signature,),
                )
                connection.commit()
        except sqlite3.Error:
            self.degraded = True

    def update_active_child(self, normalized_signature: str, active_child: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE active_leases
                    SET active_child = ?
                    WHERE normalized_signature = ?
                    """,
                    (active_child, normalized_signature),
                )
                connection.commit()
        except sqlite3.Error:
            self.degraded = True

    def new_span_id(self) -> str:
        return uuid.uuid4().hex

    def new_run_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return stamp

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def accept_sample(self, run_id: str, reason: str) -> bool:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT span_id, status FROM spans WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    return False
                if row["status"] not in {"success", "success-slow"}:
                    return False
                connection.execute(
                    """
                    UPDATE spans
                    SET accepted_for_learning = 1, quarantine_reason = NULL
                    WHERE run_id = ?
                    """,
                    (run_id,),
                )
                connection.execute(
                    """
                    INSERT INTO admin_audit(
                        action, run_id, reason, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ("accept-sample", run_id, reason, now),
                )
                connection.commit()
                return True
        except sqlite3.Error:
            self.degraded = True
            return False

    def reject_sample(self, run_id: str, reason: str) -> bool:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT span_id FROM spans WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    return False
                connection.execute(
                    """
                    UPDATE spans
                    SET accepted_for_learning = 0, quarantine_reason = ?
                    WHERE run_id = ?
                    """,
                    (f"rejected:{reason[:120]}", run_id),
                )
                connection.execute(
                    """
                    INSERT INTO admin_audit(
                        action, run_id, reason, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ("reject-sample", run_id, reason, now),
                )
                connection.commit()
                return True
        except sqlite3.Error:
            self.degraded = True
            return False
