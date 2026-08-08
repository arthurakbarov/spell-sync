#!/usr/bin/env python3
"""Thin maintainer dispatcher for config/dev-commands.json (aliases: ss, dev)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS_PATH = ROOT / "config" / "dev-commands.json"
SURFACE_PATH = ROOT / "config" / "dev-surface.json"


def _load_commands() -> dict[str, dict[str, object]]:
    payload = json.loads(COMMANDS_PATH.read_text(encoding="utf-8"))
    commands = payload.get("commands")
    if not isinstance(commands, dict):
        raise SystemExit("ss: invalid config/dev-commands.json")
    return commands  # type: ignore[return-value]


def _load_surface() -> dict[str, list[str]]:
    payload = json.loads(SURFACE_PATH.read_text(encoding="utf-8"))
    return {
        "owner": list(payload.get("ownerCommands") or []),
        "agent": list(payload.get("agentCommands") or []),
    }


def _print_help(commands: dict[str, dict[str, object]], *, agent: bool) -> int:
    surface = _load_surface()
    names = surface["agent"] if agent else surface["owner"]
    print("ss — maintainer command dispatcher")
    print("usage: ss <command> [--] [extra args...]")
    print("       ss --list")
    print("")
    for name in names:
        entry = commands.get(name) or {}
        task = entry.get("task", "")
        cmd = entry.get("command", "")
        print(f"  {name:<20} {task}")
        print(f"  {'':20} → {cmd}")
    return 0


def _resolve_command_line(template: str, extra: list[str]) -> list[str]:
    # Replace angle-bracket placeholders when extras provide values.
    parts = shlex.split(template)
    resolved: list[str] = []
    extra_i = 0
    for part in parts:
        if part.startswith("<") and part.endswith(">") and extra_i < len(extra):
            resolved.append(extra[extra_i])
            extra_i += 1
        elif part.startswith("<") and part.endswith(">"):
            raise SystemExit(f"ss: missing required argument {part}")
        else:
            resolved.append(part)
    resolved.extend(extra[extra_i:])
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    commands = _load_commands()
    if not args or args[0] in {"-h", "--help", "help"}:
        return _print_help(commands, agent="--all" in args)
    if args[0] in {"--list", "list"}:
        return _print_help(commands, agent=True)
    if args[0] == "--all":
        return _print_help(commands, agent=True)

    name = args[0]
    rest = args[1:]
    if rest[:1] == ["--"]:
        rest = rest[1:]
    entry = commands.get(name)
    if entry is None:
        print(f"ss: unknown command {name!r} (try: ss --list)", file=sys.stderr)
        return 2
    template = str(entry.get("command") or "")
    if not template:
        print(f"ss: command {name!r} has empty template", file=sys.stderr)
        return 2
    cmdline = _resolve_command_line(template, rest)
    # Ensure relative python3 scripts run from repo root.
    env = os.environ.copy()
    env.setdefault("SPELL_SYNC_TOOL", str(ROOT))
    return int(subprocess.call(cmdline, cwd=str(ROOT), env=env))


if __name__ == "__main__":
    raise SystemExit(main())
