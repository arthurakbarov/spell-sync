"""Executed-test ledger with multi-record retention."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from scripts.test_selection.digest import compute_run_key, tree_digest
from scripts.test_selection.plan_steps import PlannedStep

LEDGER_SCHEMA_VERSION = 2
INDEX_PATH = Path(".artifacts/test-runs/index.json")
HISTORY_DIR = Path(".artifacts/test-runs/history")
RETENTION_LIMIT = 100


@dataclass
class StepResult:
    kind: str
    command: list[str]
    exit_code: int
    duration_seconds: float

    def to_json_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "command": self.command,
            "exitCode": self.exit_code,
            "durationSeconds": self.duration_seconds,
        }


@dataclass(frozen=True, slots=True)
class TestRunRecord:
    schema_version: int
    run_key: str
    metadata: tuple[str, ...]
    result: str
    exit_code: int
    started_at: str
    completed_at: str
    duration_seconds: float
    tree_digest: str
    steps: tuple[StepResult, ...] = field(default_factory=tuple)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "runKey": self.run_key,
            "metadata": list(self.metadata),
            "result": self.result,
            "exitCode": self.exit_code,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "durationSeconds": self.duration_seconds,
            "treeDigest": self.tree_digest,
            "steps": [step.to_json_dict() for step in self.steps],
        }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _parse_step(item: object) -> StepResult | None:
    if not isinstance(item, dict):
        return None
    try:
        command = item.get("command")
        if not isinstance(command, list):
            return None
        return StepResult(
            kind=str(item.get("kind", "")),
            command=[str(part) for part in command],
            exit_code=int(item.get("exitCode", 1)),
            duration_seconds=float(item.get("durationSeconds", 0.0)),
        )
    except TypeError, ValueError:
        return None


def _parse_record(payload: dict[str, object]) -> TestRunRecord | None:
    try:
        metadata_raw = payload.get("metadata", [])
        if not isinstance(metadata_raw, list):
            metadata_raw = []
        steps_raw = payload.get("steps", [])
        steps: list[StepResult] = []
        if isinstance(steps_raw, list):
            for item in steps_raw:
                parsed = _parse_step(item)
                if parsed is not None:
                    steps.append(parsed)
        return TestRunRecord(
            schema_version=int(payload.get("schemaVersion", 0)),
            run_key=str(payload.get("runKey", "")),
            metadata=tuple(str(item) for item in metadata_raw),
            result=str(payload.get("result", "")),
            exit_code=int(payload.get("exitCode", 1)),
            started_at=str(payload.get("startedAt", "")),
            completed_at=str(payload.get("completedAt", "")),
            duration_seconds=float(payload.get("durationSeconds", 0.0)),
            tree_digest=str(payload.get("treeDigest", "")),
            steps=tuple(steps),
        )
    except TypeError, ValueError:
        return None


class TestRunLedger:
    def __init__(self, root: Path, index_path: Path | None = None) -> None:
        self.root = root
        self.index_path = index_path or (root / INDEX_PATH)
        self.history_dir = root / HISTORY_DIR

    def _load_index(self) -> dict[str, object]:
        if not self.index_path.is_file():
            return {"schemaVersion": LEDGER_SCHEMA_VERSION, "records": {}, "order": []}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return {"schemaVersion": LEDGER_SCHEMA_VERSION, "records": {}, "order": []}
        if not isinstance(payload, dict):
            return {"schemaVersion": LEDGER_SCHEMA_VERSION, "records": {}, "order": []}
        records = payload.get("records")
        order = payload.get("order")
        if not isinstance(records, dict):
            records = {}
        if not isinstance(order, list):
            order = []
        return {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "records": records,
            "order": order,
        }

    def _save_index(self, index: dict[str, object]) -> None:
        records = index.get("records")
        order = index.get("order")
        if not isinstance(records, dict) or not isinstance(order, list):
            return
        successful_order = [
            key
            for key in order
            if isinstance(key, str)
            and isinstance(records.get(key), dict)
            and records[key].get("result") == "success"
            and records[key].get("exitCode") == 0
        ]
        trimmed = successful_order[-RETENTION_LIMIT:]
        trimmed_records = {key: records[key] for key in trimmed if key in records}
        index = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "records": trimmed_records,
            "order": trimmed,
        }
        _atomic_write(self.index_path, json.dumps(index, indent=2) + "\n")

    def iter_records(self) -> list[TestRunRecord]:
        index = self._load_index()
        records = index.get("records")
        if not isinstance(records, dict):
            return []
        parsed: list[TestRunRecord] = []
        for payload in records.values():
            if isinstance(payload, dict):
                record = _parse_record(payload)
                if record is not None:
                    parsed.append(record)
        return parsed

    def find_success(
        self,
        *,
        run_key: str,
        steps: tuple[PlannedStep, ...],
        metadata: tuple[str, ...],
    ) -> TestRunRecord | None:
        current_digest = tree_digest(self.root)
        step_sig = tuple((step.kind, step.argv) for step in steps)
        for record in self.iter_records():
            if record.result != "success" or record.exit_code != 0:
                continue
            if record.run_key != run_key:
                continue
            if record.metadata != metadata:
                continue
            if record.tree_digest != current_digest:
                continue
            record_sig = tuple((step.kind, tuple(step.command)) for step in record.steps)
            if record_sig != step_sig:
                continue
            return record
        return None

    def record_success(
        self,
        *,
        run_key: str,
        steps: tuple[PlannedStep, ...],
        metadata: tuple[str, ...],
        started_at: datetime,
        completed_at: datetime,
        duration_seconds: float,
        validation_level: int,
        final_focused_evidence: bool,
        step_results: list[StepResult],
    ) -> TestRunRecord:
        del validation_level, final_focused_evidence
        record = TestRunRecord(
            schema_version=LEDGER_SCHEMA_VERSION,
            run_key=run_key,
            metadata=metadata,
            result="success",
            exit_code=0,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=duration_seconds,
            tree_digest=tree_digest(self.root),
            steps=tuple(step_results),
        )
        index = self._load_index()
        records = index["records"]
        order = index["order"]
        assert isinstance(records, dict)
        assert isinstance(order, list)
        records[run_key] = record.to_json_dict()
        if run_key not in order:
            order.append(run_key)
        self._save_index(index)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = completed_at.strftime("%Y%m%dT%H%M%S")
        history_path = self.history_dir / f"run-{stamp}-{run_key[:12]}.json"
        _atomic_write(history_path, json.dumps(record.to_json_dict(), indent=2) + "\n")
        return record

    def compute_key(
        self,
        *,
        steps: tuple[PlannedStep, ...],
        metadata: tuple[str, ...],
    ) -> str:
        return compute_run_key(root=self.root, steps=steps, metadata=metadata)
