"""Executed-test ledger to prevent duplicate successful runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scripts.test_selection.digest import compute_run_key, tree_digest

LEDGER_SCHEMA_VERSION = 1
DEFAULT_LEDGER_PATH = Path(".artifacts/test-runs/current.json")
HISTORY_DIR = Path(".artifacts/test-runs/history")


@dataclass(frozen=True, slots=True)
class TestRunRecord:
    schema_version: int
    run_key: str
    command: tuple[str, ...]
    result: str
    exit_code: int
    started_at: str
    completed_at: str
    duration_seconds: float
    tree_digest: str
    targets: tuple[str, ...]
    clusters: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "runKey": self.run_key,
            "command": list(self.command),
            "result": self.result,
            "exitCode": self.exit_code,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "durationSeconds": self.duration_seconds,
            "treeDigest": self.tree_digest,
            "targets": list(self.targets),
            "clusters": list(self.clusters),
        }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _parse_record(payload: dict[str, object]) -> TestRunRecord | None:
    try:
        command = payload.get("command")
        targets = payload.get("targets")
        clusters = payload.get("clusters")
        if not isinstance(command, list) or not isinstance(targets, list):
            return None
        if not isinstance(clusters, list):
            clusters = []
        return TestRunRecord(
            schema_version=int(payload.get("schemaVersion", 0)),
            run_key=str(payload.get("runKey", "")),
            command=tuple(str(item) for item in command),
            result=str(payload.get("result", "")),
            exit_code=int(payload.get("exitCode", 1)),
            started_at=str(payload.get("startedAt", "")),
            completed_at=str(payload.get("completedAt", "")),
            duration_seconds=float(payload.get("durationSeconds", 0.0)),
            tree_digest=str(payload.get("treeDigest", "")),
            targets=tuple(str(item) for item in targets),
            clusters=tuple(str(item) for item in clusters),
        )
    except (TypeError, ValueError):
        return None


class TestRunLedger:
    def __init__(self, root: Path, ledger_path: Path | None = None) -> None:
        self.root = root
        self.ledger_path = ledger_path or (root / DEFAULT_LEDGER_PATH)
        self.history_dir = root / HISTORY_DIR

    def load(self) -> TestRunRecord | None:
        if not self.ledger_path.is_file():
            return None
        try:
            payload = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return _parse_record(payload)

    def find_success(
        self,
        *,
        run_key: str,
        command: list[str],
        targets: list[str],
        clusters: list[str],
    ) -> TestRunRecord | None:
        record = self.load()
        if record is None:
            return None
        if record.result != "success" or record.exit_code != 0:
            return None
        if record.run_key != run_key:
            return None
        if list(record.command) != command:
            return None
        if list(record.targets) != sorted(targets):
            return None
        if list(record.clusters) != sorted(clusters):
            return None
        current_digest = tree_digest(self.root, tracked_paths=None)
        if record.tree_digest != current_digest:
            return None
        return record

    def record_success(
        self,
        *,
        run_key: str,
        command: list[str],
        targets: list[str],
        clusters: list[str],
        started_at: datetime,
        completed_at: datetime,
        duration_seconds: float,
    ) -> TestRunRecord:
        record = TestRunRecord(
            schema_version=LEDGER_SCHEMA_VERSION,
            run_key=run_key,
            command=tuple(command),
            result="success",
            exit_code=0,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=duration_seconds,
            tree_digest=tree_digest(self.root, tracked_paths=None),
            targets=tuple(sorted(targets)),
            clusters=tuple(sorted(clusters)),
        )
        text = json.dumps(record.to_json_dict(), indent=2) + "\n"
        _atomic_write(self.ledger_path, text)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = completed_at.strftime("%Y%m%dT%H%M%S")
        history_path = self.history_dir / f"run-{stamp}-{run_key[:12]}.json"
        _atomic_write(history_path, text)
        return record

    def compute_key(
        self,
        *,
        command: list[str],
        targets: list[str],
        clusters: list[str],
    ) -> str:
        return compute_run_key(
            root=self.root,
            command=command,
            targets=targets,
            clusters=clusters,
            tree_paths=None,
        )
