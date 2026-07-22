#!/usr/bin/env python3
"""Run platform/Python compatibility checks without full CI duplication."""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_UV_VERSION_PATTERN = re.compile(r"uv\s+(\d+\.\d+\.\d+)")


def _run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        if output and not output.endswith("\n"):
            output += "\n"
        output += proc.stderr
    return proc.returncode, output.rstrip()


def _resolve_uv_executable() -> str:
    uv = shutil.which("uv")
    if uv:
        return uv
    return "uv"


def _normalize_platform(value: str) -> str:
    mapping = {
        "linux": "linux",
        "darwin": "macos",
        "macos": "macos",
        "win32": "windows",
        "windows": "windows",
    }
    return mapping.get(value.lower(), value.lower())


def _actual_platform() -> str:
    return _normalize_platform(platform.system())


def _actual_python_version() -> str:
    return platform.python_version()


def _verify_runtime_identity(*, platform_arg: str, python_version_arg: str) -> str | None:
    actual_platform = _actual_platform()
    expected_platform = _normalize_platform(platform_arg)
    if actual_platform != expected_platform:
        return "compatibility.environment-mismatch"
    actual_python = _actual_python_version()
    if not actual_python.startswith(python_version_arg):
        return "compatibility.environment-mismatch"
    implementation = platform.python_implementation().lower()
    if implementation != "cpython":
        return "compatibility.environment-mismatch"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run compatibility checks for matrix cell.")
    parser.add_argument("--platform", required=True, choices=("linux", "macos", "windows"))
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--experimental", action="store_true")
    args = parser.parse_args(argv)

    mismatch = _verify_runtime_identity(
        platform_arg=args.platform,
        python_version_arg=args.python_version,
    )
    if mismatch is not None:
        execution_id = f"compatibility:{args.platform}-py{args.python_version.replace('.', '')}"
        payload = {
            "executionId": execution_id,
            "platform": args.platform,
            "pythonVersion": args.python_version,
            "actualPlatform": _actual_platform(),
            "actualPythonVersion": _actual_python_version(),
            "experimental": args.experimental,
            "exitCode": 1,
            "failedId": mismatch,
            "steps": [],
        }
        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"COMPATIBILITY_FAILED_ID={mismatch}")
            print("COMPATIBILITY_RESULT=failed")
            print("COMPATIBILITY_EXIT=1")
        return 1

    py = sys.executable
    uv = _resolve_uv_executable()
    execution_id = f"compatibility:{args.platform}-py{args.python_version.replace('.', '')}"
    if args.experimental:
        execution_id += "-experimental"
    steps = [
        ("environment-contract", [py, "scripts/validate_environment_contract.py"]),
        ("lock-check", [uv, "lock", "--check"]),
        (
            "product-core",
            [py, "-m", "pytest", "tests/test_core.py", "-q"],
        ),
        (
            "cli-json-contracts",
            [
                py,
                "-m",
                "pytest",
                "tests/test_cli.py",
                "tests/test_json_contract.py",
                "-q",
            ],
        ),
        (
            "platform-target-discovery",
            [py, "-m", "pytest", "tests/test_dictionaries.py", "-q", "-k", "discovery"],
        ),
        (
            "platform-filesystem",
            [py, "-m", "pytest", "tests/test_edge_cases.py", "-q", "-k", "path"],
        ),
        ("installed-wheel-import", [py, "-m", "spell_sync.cli", "version"]),
        ("cli-smoke", [py, "-m", "spell_sync.cli", "version"]),
    ]
    if args.platform in {"linux", "macos"}:
        steps.append(
            (
                "tui-smoke",
                [py, "-m", "pytest", "tests/tui/test_architecture.py", "-q"],
            )
        )
    results: list[dict[str, object]] = []
    exit_code = 0
    failed_id = ""
    for step_id, command in steps:
        rc, output = _run(command)
        results.append({"step": step_id, "exitCode": rc, "outputLines": len(output.splitlines())})
        if rc != 0:
            exit_code = rc
            failed_id = f"compatibility.{step_id}-failed"
            break
    payload = {
        "executionId": execution_id,
        "platform": args.platform,
        "pythonVersion": args.python_version,
        "actualPlatform": _actual_platform(),
        "actualPythonVersion": _actual_python_version(),
        "experimental": args.experimental,
        "exitCode": exit_code,
        "failedId": failed_id,
        "steps": results,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"COMPATIBILITY_EXECUTION_ID={execution_id}")
        print(f"COMPATIBILITY_RESULT={'success' if exit_code == 0 else 'failed'}")
        if failed_id:
            print(f"COMPATIBILITY_FAILED_ID={failed_id}")
        print(f"COMPATIBILITY_EXIT={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
