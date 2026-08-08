"""dev_runs index JSONL journal persistence."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import dev_runs


def test_append_journal_dedupes_ci_run_ids(tmp_path: Path) -> None:
    journal = tmp_path / "runs-index.jsonl"
    entries = [
        {"kind": "ci", "runId": "run-1", "result": "success"},
        {"kind": "span", "runId": "x", "executionId": "e1"},
        {"kind": "ci", "runId": "run-1", "result": "success"},
        {"kind": "ci", "runId": "run-2", "result": "failed"},
    ]
    written = dev_runs._append_journal(journal, entries)
    assert written == 2
    written_again = dev_runs._append_journal(journal, entries)
    assert written_again == 0
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [row["runId"] for row in lines] == ["run-1", "run-2"]
