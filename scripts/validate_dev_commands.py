#!/usr/bin/env python3
"""Validate config/dev-commands.json and config/dev-surface.json parity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS_PATH = ROOT / "config" / "dev-commands.json"
SURFACE_PATH = ROOT / "config" / "dev-surface.json"
MARKER_START = "[dev-commands:start]"
MARKER_END = "[dev-commands:end]"
CI_CHECKS_START = "[ci-checks:start]"
CI_CHECKS_END = "[ci-checks:end]"
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
    surface_names: set[str] = set()
    for field in ("ownerCommands", "agentCommands"):
        listed = surface.get(field)
        if not isinstance(listed, list) or not listed:
            errors.append(f"dev-surface.json: {field} must be a non-empty list")
            continue
        for name in listed:
            if name not in commands:
                errors.append(f"dev-surface.json: unknown {field} entry {name!r}")
            else:
                surface_names.add(name)
    for name in sorted(commands):
        if name not in surface_names:
            errors.append(
                f"dev-surface.json: command {name!r} missing from ownerCommands and agentCommands"
            )
    if not DEV_DOC.is_file():
        errors.append("docs/DEVELOPMENT.md missing")
    else:
        text = DEV_DOC.read_text(encoding="utf-8")
        if MARKER_START not in text or MARKER_END not in text:
            errors.append(
                "docs/DEVELOPMENT.md missing [dev-commands:start]/[dev-commands:end] markers"
            )
        if CI_CHECKS_START not in text or CI_CHECKS_END not in text:
            errors.append("docs/DEVELOPMENT.md missing [ci-checks:start]/[ci-checks:end] markers")
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


def _list_ci_check_ids() -> list[str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ci_runner.py"), "--list-checks"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ci_runner --list-checks failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def render_ci_checks(ids: list[str]) -> str:
    lines = [
        "| # | Check ID |",
        "|---|----------|",
    ]
    for index, check_id in enumerate(ids, start=1):
        lines.append(f"| {index} | `{check_id}` |")
    return "\n".join(lines)


def _replace_fence(text: str, start: str, end: str, body: str) -> str:
    if start not in text or end not in text:
        raise ValueError(f"missing markers {start}/{end}")
    start_idx = text.index(start) + len(start)
    end_idx = text.index(end)
    return text[:start_idx] + "\n" + body + "\n" + text[end_idx:]


def sync_doc(*, write: bool) -> list[str]:
    errors = validate()
    if errors:
        return errors
    commands = _load(COMMANDS_PATH)["commands"]
    assert isinstance(commands, dict)
    table = render_table(commands)
    try:
        checks = render_ci_checks(_list_ci_check_ids())
    except RuntimeError as exc:
        return [str(exc)]
    text = DEV_DOC.read_text(encoding="utf-8")
    try:
        desired = _replace_fence(text, MARKER_START, MARKER_END, table)
        desired = _replace_fence(desired, CI_CHECKS_START, CI_CHECKS_END, checks)
    except ValueError as exc:
        return [str(exc)]
    if desired == text:
        return []
    if not write:
        return [
            "docs/DEVELOPMENT.md generated command/ci-checks tables are stale; run with --write"
        ]
    DEV_DOC.write_text(desired, encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    write = "--write" in args
    # Default and --check both detect stale generated fences; --write rewrites them.
    errors = sync_doc(write=write)
    if write:
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
