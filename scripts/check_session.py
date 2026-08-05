#!/usr/bin/env python3
"""Ephemeral agent check-session ledger for reuse within one arc.

Sessions live under SPELL_SYNC_CHECK_SESSION_DIR (default
/tmp/spell-sync-agent-session). They are not committed.

Fingerprint is HEAD + porcelain for the repository root. A successful
``record`` may be reused via ``lookup`` only when the fingerprint still matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DIR = Path("/tmp/spell-sync-agent-session")
_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_dir() -> Path:
    raw = os.environ.get("SPELL_SYNC_CHECK_SESSION_DIR")
    return Path(raw) if raw else DEFAULT_BASE_DIR


def _sanitize_id(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", value.strip()).strip("-")
    return cleaned or "session"


def _current_file(base: Path) -> Path:
    return base / ".current-session"


def _session_dir(base: Path, session_id: str) -> Path:
    return base / _sanitize_id(session_id)


def _ledger_path(base: Path, session_id: str) -> Path:
    return _session_dir(base, session_id) / "ledger.jsonl"


def _meta_path(base: Path, session_id: str) -> Path:
    return _session_dir(base, session_id) / "session.json"


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def tree_fingerprint(root: Path | None = None) -> str:
    """Stable fingerprint of committed HEAD plus dirty porcelain."""
    repo = root or ROOT
    head = _git(repo, "rev-parse", "HEAD").strip() or "unknown"
    porcelain = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    payload = f"{head}\0{porcelain}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_session_id(explicit: str | None = None, *, base: Path | None = None) -> str:
    if os.environ.get("SPELL_SYNC_CHECK_SESSION_ID"):
        return _sanitize_id(os.environ["SPELL_SYNC_CHECK_SESSION_ID"])
    if explicit:
        return _sanitize_id(explicit)
    if os.environ.get("CURSOR_TRACE_ID"):
        return _sanitize_id(os.environ["CURSOR_TRACE_ID"])
    base_dir = base or _base_dir()
    current = _current_file(base_dir)
    if current.is_file():
        return _sanitize_id(current.read_text(encoding="utf-8").strip())
    return _sanitize_id(f"pid-{os.getpid()}")


def start_session(
    *,
    session_id: str | None = None,
    base: Path | None = None,
) -> str:
    base_dir = base or _base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    if (
        session_id
        or os.environ.get("SPELL_SYNC_CHECK_SESSION_ID")
        or os.environ.get("CURSOR_TRACE_ID")
    ):
        sid = resolve_session_id(session_id, base=base_dir)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sid = _sanitize_id(f"arc-{stamp}-{os.getpid()}")
    directory = _session_dir(base_dir, sid)
    directory.mkdir(parents=True, exist_ok=True)
    _current_file(base_dir).write_text(sid, encoding="utf-8")
    meta = {
        "sessionId": sid,
        "startedAt": _utc_now(),
        "status": "active",
    }
    _meta_path(base_dir, sid).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return sid


def finish_session(session_id: str | None = None, *, base: Path | None = None) -> str:
    base_dir = base or _base_dir()
    sid = resolve_session_id(session_id, base=base_dir)
    directory = _session_dir(base_dir, sid)
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = _meta_path(base_dir, sid)
    finished_at = _utc_now()
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {"sessionId": sid}
    else:
        meta = {"sessionId": sid}
    if not isinstance(meta, dict):
        meta = {"sessionId": sid}
    meta["finishedAt"] = finished_at
    meta["status"] = "finished"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    current = _current_file(base_dir)
    if current.is_file() and current.read_text(encoding="utf-8").strip() == sid:
        current.unlink(missing_ok=True)
    return sid


def read_ledger(session_id: str, *, base: Path | None = None) -> list[dict[str, Any]]:
    path = _ledger_path(base or _base_dir(), session_id)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def record_check(
    check_id: str,
    *,
    exit_code: int,
    duration: float = 0.0,
    selected_by: str = "",
    reused: bool = False,
    session_id: str | None = None,
    root: Path | None = None,
    base: Path | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    base_dir = base or _base_dir()
    sid = resolve_session_id(session_id, base=base_dir)
    directory = _session_dir(base_dir, sid)
    directory.mkdir(parents=True, exist_ok=True)
    fp = fingerprint if fingerprint is not None else tree_fingerprint(root or ROOT)
    now = _utc_now()
    entry: dict[str, Any] = {
        "id": check_id,
        "exitCode": int(exit_code),
        "fingerprint": fp,
        "startedAt": now,
        "completedAt": now,
        "duration": float(duration),
        "selectedBy": selected_by,
        "sessionId": sid,
        "reused": bool(reused),
    }
    ledger = _ledger_path(base_dir, sid)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def lookup_reusable(
    check_id: str,
    *,
    session_id: str | None = None,
    root: Path | None = None,
    base: Path | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any] | None:
    base_dir = base or _base_dir()
    sid = resolve_session_id(session_id, base=base_dir)
    fp = fingerprint if fingerprint is not None else tree_fingerprint(root or ROOT)
    for entry in read_ledger(sid, base=base_dir):
        if (
            entry.get("id") == check_id
            and entry.get("fingerprint") == fp
            and entry.get("exitCode") == 0
            and entry.get("reused") is False
        ):
            return entry
    return None


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start", help="start a session and set it current")
    start_p.add_argument("--session-id", default=None)
    start_p.add_argument("--json", action="store_true")

    status_p = sub.add_parser("status", help="print ledger for a session")
    status_p.add_argument("session_id", nargs="?", default=None)
    status_p.add_argument("--session-id", dest="session_id_opt", default=None)
    status_p.add_argument("--json", action="store_true")

    finish_p = sub.add_parser("finish", help="mark a session finished")
    finish_p.add_argument("session_id", nargs="?", default=None)
    finish_p.add_argument("--session-id", dest="session_id_opt", default=None)
    finish_p.add_argument("--json", action="store_true")

    record_p = sub.add_parser("record", help="append a check result to the ledger")
    record_p.add_argument("check_id")
    record_p.add_argument("--exit-code", type=int, required=True)
    record_p.add_argument("--duration", type=float, default=0.0)
    record_p.add_argument("--selected-by", default="")
    record_p.add_argument("--session-id", default=None)
    record_p.add_argument("--repo-root", type=Path, default=ROOT)
    record_p.add_argument("--json", action="store_true")

    lookup_p = sub.add_parser("lookup", help="reuse a successful matching check")
    lookup_p.add_argument("check_id")
    lookup_p.add_argument("--session-id", default=None)
    lookup_p.add_argument("--repo-root", type=Path, default=ROOT)
    lookup_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "start":
        sid = start_session(session_id=args.session_id)
        if args.json:
            _print_json({"sessionId": sid, "status": "started"})
        else:
            print(f"session: {sid}")
        return 0

    if args.command == "status":
        session_arg = args.session_id_opt or args.session_id
        sid = resolve_session_id(session_arg)
        entries = read_ledger(sid)
        if args.json:
            _print_json({"sessionId": sid, "entries": entries})
        else:
            print(f"session: {sid}")
            if entries:
                for entry in entries:
                    print(json.dumps(entry, sort_keys=True))
            else:
                print("(empty ledger)")
        return 0

    if args.command == "finish":
        session_arg = args.session_id_opt or args.session_id
        sid = finish_session(session_arg)
        if args.json:
            _print_json({"sessionId": sid, "status": "finished"})
        else:
            print(f"session finished: {sid}")
        return 0

    if args.command == "record":
        entry = record_check(
            args.check_id,
            exit_code=args.exit_code,
            duration=args.duration,
            selected_by=args.selected_by,
            session_id=args.session_id,
            root=args.repo_root,
        )
        if args.json:
            _print_json(entry)
        else:
            print(f"recorded: {args.check_id} exit={args.exit_code}")
        return 0

    cached = lookup_reusable(
        args.check_id,
        session_id=args.session_id,
        root=args.repo_root,
    )
    if cached is None:
        if args.json:
            _print_json({"reusable": False, "checkId": args.check_id})
        else:
            print(f"no reusable result: {args.check_id}")
        return 1
    if args.json:
        payload = dict(cached)
        payload["reusable"] = True
        _print_json(payload)
    else:
        print(f"reuse: {args.check_id} ({cached.get('duration', 0)}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
