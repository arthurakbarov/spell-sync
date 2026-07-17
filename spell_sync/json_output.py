"""JSON output for --json."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from .sync_run import DictionaryDiff, PushResult

SCHEMA_VERSION = 1


def emit_json(payload: Dict[str, Any]) -> None:
    if "command" not in payload or "exit" not in payload:
        missing = [k for k in ("command", "exit") if k not in payload]
        raise ValueError(f"JSON payload missing keys: {', '.join(missing)}")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def base_payload(command: str, *, exit: int) -> Dict[str, Any]:
    """Common JSON keys shared by all commands."""
    return {"schema_version": SCHEMA_VERSION, "command": command, "exit": exit}


def push_result_payload(result: PushResult) -> Dict[str, Any]:
    return {
        "word_count": result.word_count,
        "written": list(result.written),
        "skipped": list(result.skipped),
        "skipped_reasons": dict(result.skipped_reasons),
        "skipped_details": dict(result.skipped_details),
    }


def dictionary_diff_payload(diff: DictionaryDiff) -> Dict[str, Any]:
    return {
        "name": diff.name,
        "target_count": diff.target_count,
        "local_count": diff.local_count,
        "to_add": diff.to_add,
        "to_remove": diff.to_remove,
        "add_words": list(diff.add_words),
        "remove_words": list(diff.remove_words),
    }
