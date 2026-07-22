#!/usr/bin/env python3
"""Run a registered development command under execution budget control."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.controller import run_monitored_command  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command under execution budget control.")
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--mode", default="exact")
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--test-files", type=int, default=0)
    parser.add_argument("--test-nodes", type=int, default=0)
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--tui", action="store_true")
    parser.add_argument("--packaging", action="store_true")
    parser.add_argument("--enforce-stall", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("command required")
    exit_code, _timing = run_monitored_command(
        ROOT,
        execution_id=args.execution_id,
        command=args.command,
        mode=args.mode,
        required=args.required,
        test_file_count=args.test_files,
        test_node_count=args.test_nodes,
        coverage=args.coverage,
        tui=args.tui,
        packaging=args.packaging,
        enforce_stall=args.enforce_stall,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
