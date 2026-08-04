#!/usr/bin/env python3
"""Validate config/dev-commands.json and config/dev-surface.json parity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS_PATH = ROOT / "config" / "dev-commands.json"
SURFACE_PATH = ROOT / "config" / "dev-surface.json"
MARKER_START = "[dev-commands:start]"
MARKER_END = "[dev-commands:end]"
DEV_DOC = ROOT / "docs" / "DEVELOPMENT.md"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be an object")
    return payload


def validate() -> list[str]:
    errors: list[str] = []
    commands_doc = _load(COMMANDS_PATH)
    surface = _load(SURFACE_PATH)
    commands = commands_doc.get("commands")
    if not isinstance(commands, dict) or not commands:
        errors.append("dev-commands.json: commands object required")
        return errors
    for key, entry in commands.items():
        if not isinstance(entry, dict):
            errors.append(f"dev-commands.json: {key} must be an object")
            continue
        for field in ("command", "stage", "task"):
            if not isinstance(entry.get(field), str) or not entry.get(field):
                errors.append(f"dev-commands.json: {key}.{field} required")
    for field in ("ownerCommands", "agentCommands"):
        listed = surface.get(field)
        if not isinstance(listed, list) or not listed:
            errors.append(f"dev-surface.json: {field} must be a non-empty list")
            continue
        for name in listed:
            if name not in commands:
                errors.append(f"dev-surface.json: unknown {field} entry {name!r}")
    if not DEV_DOC.is_file():
        errors.append("docs/DEVELOPMENT.md missing")
    else:
        text = DEV_DOC.read_text(encoding="utf-8")
        if MARKER_START not in text or MARKER_END not in text:
            errors.append(
                "docs/DEVELOPMENT.md missing [dev-commands:start]/[dev-commands:end] markers"
            )
    return errors


def render_table(commands: dict[str, dict]) -> str:
    lines = [
        "| Task | Command | Stage |",
        "|------|---------|-------|",
    ]
    for key in sorted(commands, key=lambda item: (commands[item].get("stage", ""), item)):
        entry = commands[key]
        task = str(entry.get("task", key)).replace("|", "\\|")
        command = str(entry.get("command", "")).replace("|", "\\|")
        stage = str(entry.get("stage", "")).replace("|", "\\|")
        lines.append(f"| {task} | `{command}` | {stage} |")
    return "\n".join(lines)


def sync_doc(*, write: bool) -> list[str]:
    errors = validate()
    if errors:
        return errors
    commands = _load(COMMANDS_PATH)["commands"]
    assert isinstance(commands, dict)
    table = render_table(commands)
    text = DEV_DOC.read_text(encoding="utf-8")
    start = text.index(MARKER_START) + len(MARKER_START)
    end = text.index(MARKER_END)
    current = text[start:end].strip("\n")
    desired = table
    if current == desired:
        return []
    if not write:
        return ["docs/DEVELOPMENT.md generated command table is stale; run with --write"]
    updated = text[:start] + "\n" + desired + "\n" + text[end:]
    DEV_DOC.write_text(updated, encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    write = "--write" in (argv or sys.argv[1:])
    errors = sync_doc(write=write) if write or "--check" in (argv or sys.argv[1:]) else validate()
    if write:
        # re-validate after write
        errors = validate()
    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        print("DEV_COMMANDS_VALIDATION=failed")
        return 1
    print("DEV_COMMANDS_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
