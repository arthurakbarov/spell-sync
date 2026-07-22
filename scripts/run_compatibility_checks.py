#!/usr/bin/env python3
"""Run platform/Python compatibility checks without full CI duplication."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        if output and not output.endswith("\n"):
            output += "\n"
        output += proc.stderr
    return proc.returncode, output.rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run compatibility checks for matrix cell.")
    parser.add_argument("--platform", required=True, choices=("linux", "macos", "windows"))
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--experimental", action="store_true")
    args = parser.parse_args(argv)
    py = sys.executable
    execution_id = f"compatibility:{args.platform}-py{args.python_version.replace('.', '')}"
    if args.experimental:
        execution_id += "-experimental"
    steps = [
        ("environment-contract", [py, "scripts/validate_environment_contract.py"]),
        ("lock-check", [py, "-m", "uv", "lock", "--check"]),
        (
            "product-pytest",
            [
                py,
                "-m",
                "pytest",
                "tests/test_core.py",
                "tests/test_cli.py",
                "tests/test_json_contract.py",
                "-q",
            ],
        ),
        ("cli-smoke", [py, "-m", "spell_sync.cli", "version"]),
    ]
    results: list[dict[str, object]] = []
    exit_code = 0
    for step_id, command in steps:
        rc, output = _run(command)
        results.append({"step": step_id, "exitCode": rc})
        if rc != 0:
            exit_code = rc
            break
    payload = {
        "executionId": execution_id,
        "platform": args.platform,
        "pythonVersion": args.python_version,
        "experimental": args.experimental,
        "exitCode": exit_code,
        "steps": results,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"COMPATIBILITY_EXECUTION_ID={execution_id}")
        print(f"COMPATIBILITY_RESULT={'success' if exit_code == 0 else 'failed'}")
        print(f"COMPATIBILITY_EXIT={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
