#!/usr/bin/env python3
"""Run platform/Python compatibility checks without full CI duplication."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_UV_VERSION_PATTERN = re.compile(r"uv\s+(\d+\.\d+\.\d+)")


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=cwd or ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
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


def _venv_python(venv_dir: Path) -> Path:
    for name in ("python", "python3"):
        candidate = venv_dir / "bin" / name
        if candidate.is_file():
            return candidate
    candidate = venv_dir / "Scripts" / "python.exe"
    if candidate.is_file():
        return candidate
    raise RuntimeError("compatibility.wheel-venv-failed")


def _run_wheel_compatibility(host_python: str) -> tuple[list[dict[str, object]], int, str]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="spell-sync-compat-") as tmp:
        tmp_path = Path(tmp)
        build_dir = tmp_path / "dist"
        build_dir.mkdir()
        venv_dir = tmp_path / "venv"
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        rc, output = _run(
            [host_python, "-m", "build", "-w", "-n", "--outdir", str(build_dir)],
            cwd=ROOT,
        )
        results.append(
            {
                "step": "compatibility.wheel-build",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0:
            return results, rc, "compatibility.wheel-build-failed"

        wheels = sorted(build_dir.glob("*.whl"))
        if not wheels:
            return results, 1, "compatibility.wheel-build-failed"

        rc, output = _run([host_python, "-m", "venv", str(venv_dir)])
        results.append(
            {
                "step": "compatibility.wheel-venv",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0:
            return results, rc, "compatibility.wheel-venv-failed"

        venv_py = _venv_python(venv_dir)
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        rc, output = _run(
            [str(venv_py), "-m", "pip", "install", "-q", str(wheels[0])],
            env=clean_env,
        )
        results.append(
            {
                "step": "compatibility.wheel-install",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0:
            return results, rc, "compatibility.wheel-install-failed"

        origin_script = (
            "import pathlib, spell_sync, sys; "
            f"root = pathlib.Path({str(ROOT)!r}).resolve(); "
            "origin = pathlib.Path(spell_sync.__file__).resolve(); "
            "print(origin); "
            "print(str(origin).startswith(str(root)))"
        )
        rc, output = _run(
            [str(venv_py), "-c", origin_script],
            cwd=work_dir,
            env=clean_env,
        )
        results.append(
            {
                "step": "compatibility.wheel-origin",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0:
            return results, rc, "compatibility.wheel-origin-failed"
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) < 2 or lines[1].lower() == "true":
            return results, 1, "compatibility.wheel-origin-failed"

        rc, output = _run(
            [str(venv_py), "-m", "spell_sync", "version"],
            cwd=work_dir,
            env=clean_env,
        )
        results.append(
            {
                "step": "compatibility.wheel-version",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0 or "0.2.1" not in output:
            return results, 1, "compatibility.wheel-version-failed"

        rc, output = _run(
            [str(venv_py), "-m", "spell_sync", "--help"],
            cwd=work_dir,
            env=clean_env,
        )
        results.append(
            {
                "step": "compatibility.wheel-cli",
                "exitCode": rc,
                "outputLines": len(output.splitlines()),
            }
        )
        if rc != 0 or "pull" not in output.lower():
            return results, 1, "compatibility.wheel-cli-failed"

    return results, 0, ""


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
        ("product-core", [py, "-m", "pytest", "tests/test_core.py", "-q"]),
        (
            "cli-json-contracts",
            [py, "-m", "pytest", "tests/test_cli.py", "tests/test_json_contract.py", "-q"],
        ),
        (
            "platform-target-discovery",
            [py, "-m", "pytest", "tests/test_dictionaries.py", "-q", "-k", "discovery"],
        ),
        (
            "platform-filesystem",
            [py, "-m", "pytest", "tests/test_edge_cases.py", "-q", "-k", "path"],
        ),
    ]
    if args.platform in {"linux", "macos"}:
        steps.append(("tui-smoke", [py, "-m", "pytest", "tests/tui/test_architecture.py", "-q"]))
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
    else:
        wheel_results, wheel_rc, wheel_failed = _run_wheel_compatibility(py)
        results.extend(wheel_results)
        if wheel_rc != 0:
            exit_code = wheel_rc
            failed_id = wheel_failed
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
