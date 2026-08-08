#!/usr/bin/env python3
"""Triage recent execution and CI runs (nix-style runs show / failures)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.state_paths import history_database_path  # noqa: E402

DEFAULT_RUNS_JOURNAL = ROOT / ".artifacts" / "ci" / "runs-index.jsonl"

_FAILURE_STATUSES = frozenset(
    {
        "failed",
        "timeout-hard",
        "timeout-stall",
        "timeout-soft",
        "interrupted",
        "blocked-admission",
        "blocked-duplicate",
    }
)


def _ci_summaries() -> list[Path]:
    artifacts = ROOT / ".artifacts" / "ci"
    if not artifacts.is_dir():
        return []
    paths = sorted(artifacts.glob("ci-summary-*.json"), reverse=True)
    current = artifacts / "ci-summary.json"
    if current.is_file():
        paths = [current, *[p for p in paths if p.resolve() != current.resolve()]]
    return paths


def cmd_failures(*, limit: int, as_json: bool) -> int:
    store = HistoryStore.open()
    try:
        spans = store.fetch_report_spans(limit=max(limit * 5, 100))
    finally:
        store.close()
    failed = [row for row in spans if str(row.get("status", "")) in _FAILURE_STATUSES]
    failed = failed[:limit]
    if as_json:
        print(json.dumps({"failures": failed}, indent=2, sort_keys=True))
        return 0
    if not failed:
        print("DEV_RUNS_FAILURES=0")
        return 0
    print(f"DEV_RUNS_FAILURES={len(failed)}")
    for row in failed:
        print(
            f"{row.get('start_time', '')}\t{row.get('execution_id', '')}\t"
            f"{row.get('status', '')}\t{row.get('duration_seconds', '')}"
        )
    return 0


def cmd_show(run_id: str, *, as_json: bool) -> int:
    payload: dict[str, object] = {"runId": run_id, "spans": [], "ciSummary": None}
    db = history_database_path()
    if db.is_file():
        connection = sqlite3.connect(db)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT run_id, span_id, execution_id, status, exit_code,
                       duration_seconds, start_time, end_time, active_child_at_end,
                       quarantine_reason
                FROM spans
                WHERE run_id = ? OR span_id = ?
                ORDER BY start_time ASC
                """,
                (run_id, run_id),
            ).fetchall()
            payload["spans"] = [dict(row) for row in rows]
        finally:
            connection.close()

    for path in _ci_summaries():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("runId") == run_id or data.get("gitHead", "").startswith(run_id):
            payload["ciSummary"] = {
                "path": str(path),
                "result": data.get("result"),
                "gitHead": data.get("gitHead"),
                "mode": data.get("mode"),
                "finalEvidence": data.get("finalEvidence"),
                "logPath": data.get("logPath"),
            }
            break

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        spans = payload["spans"]
        assert isinstance(spans, list)
        print(f"DEV_RUNS_RUN_ID={run_id}")
        print(f"DEV_RUNS_SPAN_COUNT={len(spans)}")
        for row in spans:
            assert isinstance(row, dict)
            print(
                f"{row.get('execution_id')}\t{row.get('status')}\t"
                f"exit={row.get('exit_code')}\t{row.get('duration_seconds')}s"
            )
        ci = payload["ciSummary"]
        if isinstance(ci, dict):
            print(f"DEV_RUNS_CI_RESULT={ci.get('result')}")
            print(f"DEV_RUNS_CI_LOG={ci.get('logPath') or ''}")
            print(f"DEV_RUNS_CI_SUMMARY={ci.get('path')}")
        elif not spans:
            print("DEV_RUNS_RESULT=not-found", file=sys.stderr)
            return 1
    return 0


def cmd_list(*, limit: int, as_json: bool) -> int:
    store = HistoryStore.open()
    try:
        spans = store.fetch_report_spans(limit=limit)
    finally:
        store.close()
    if as_json:
        print(json.dumps({"spans": spans}, indent=2, sort_keys=True))
        return 0
    print(f"DEV_RUNS_LIST={len(spans)}")
    for row in spans:
        print(
            f"{row.get('start_time', '')}\t{row.get('execution_id', '')}\t"
            f"{row.get('status', '')}\t{row.get('duration_seconds', '')}"
        )
    return 0


def _append_journal(journal: Path, entries: list[dict[str, object]]) -> int:
    """Append unique CI runIds to a JSONL journal; return newly written lines."""
    journal.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if journal.is_file():
        for line in journal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("kind") == "ci":
                run_id = row.get("runId")
                if isinstance(run_id, str) and run_id:
                    seen.add(run_id)
    written = 0
    with journal.open("a", encoding="utf-8") as handle:
        for item in entries:
            if item.get("kind") != "ci":
                continue
            run_id = item.get("runId")
            if not isinstance(run_id, str) or not run_id or run_id in seen:
                continue
            handle.write(json.dumps(item, sort_keys=True) + "\n")
            seen.add(run_id)
            written += 1
    return written


def cmd_index(
    *,
    limit: int,
    as_json: bool,
    journal: Path | None,
    persist: bool,
) -> int:
    """Chronological index of CI summaries plus recent execution spans."""
    entries: list[dict[str, object]] = []
    for path in _ci_summaries()[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        entries.append(
            {
                "kind": "ci",
                "runId": data.get("runId"),
                "result": data.get("result"),
                "gitHead": data.get("gitHead"),
                "startedAt": data.get("startedAt"),
                "completedAt": data.get("completedAt"),
                "path": str(path),
                "logPath": data.get("logPath"),
            }
        )
    store = HistoryStore.open()
    try:
        spans = store.fetch_report_spans(limit=limit)
    finally:
        store.close()
    for row in spans:
        entries.append(
            {
                "kind": "span",
                "runId": row.get("run_id"),
                "executionId": row.get("execution_id"),
                "status": row.get("status"),
                "startedAt": row.get("start_time"),
                "durationSeconds": row.get("duration_seconds"),
            }
        )
    entries = entries[:limit]
    journal_path = journal or DEFAULT_RUNS_JOURNAL
    written = 0
    if persist:
        written = _append_journal(journal_path, entries)
    if as_json:
        print(
            json.dumps(
                {
                    "index": entries,
                    "journalPath": str(journal_path),
                    "journalAppended": written,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"DEV_RUNS_INDEX={len(entries)}")
    print(f"DEV_RUNS_JOURNAL={journal_path}")
    print(f"DEV_RUNS_JOURNAL_APPENDED={written}")
    for item in entries:
        kind = item.get("kind")
        if kind == "ci":
            head = str(item.get("gitHead") or "")
            print(f"ci\t{item.get('runId')}\t{item.get('result')}\t{head[:12]}\t{item.get('path')}")
        else:
            print(
                f"span\t{item.get('runId')}\t{item.get('executionId')}\t"
                f"{item.get('status')}\t{item.get('durationSeconds')}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Triage execution and CI runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    failures = sub.add_parser("failures", help="List recent failed spans")
    failures.add_argument("--limit", type=int, default=20)
    failures.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show spans / CI summary for a run id")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")

    listing = sub.add_parser("list", help="List recent spans")
    listing.add_argument("--limit", type=int, default=30)
    listing.add_argument("--json", action="store_true")

    index = sub.add_parser("index", help="Chronological CI + span index")
    index.add_argument("--limit", type=int, default=40)
    index.add_argument("--json", action="store_true")
    index.add_argument(
        "--journal",
        type=Path,
        default=None,
        help=f"JSONL journal path (default: {DEFAULT_RUNS_JOURNAL})",
    )
    index.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not append CI rows to the JSONL journal",
    )

    args = parser.parse_args(argv)
    if args.command == "failures":
        return cmd_failures(limit=args.limit, as_json=args.json)
    if args.command == "show":
        return cmd_show(args.run_id, as_json=args.json)
    if args.command == "list":
        return cmd_list(limit=args.limit, as_json=args.json)
    if args.command == "index":
        return cmd_index(
            limit=args.limit,
            as_json=args.json,
            journal=args.journal,
            persist=not args.no_persist,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
