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
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT


def _expected_package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    return version if isinstance(version, str) else ""


_EXPECTED_VERSION = _expected_package_version()

_WHEEL_ENV_KEYS_TO_CLEAR = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
    "__PYVENV_LAUNCHER__",
)

_ORIGIN_PROBE_SCRIPT = """
import json
import pathlib
import sys
import sysconfig
import spell_sync

payload = {
    "origin": str(pathlib.Path(spell_sync.__file__).resolve()),
    "executable": str(
        pathlib.Path(sysconfig.get_path("scripts")) / pathlib.Path(sys.executable).name
    ),
    "sysPrefix": sys.prefix,
    "basePrefix": getattr(sys, "base_prefix", sys.prefix),
    "purelib": sysconfig.get_path("purelib"),
    "platlib": sysconfig.get_path("platlib"),
    "version": spell_sync.__version__,
}
print(json.dumps(payload))
"""


def _path_within(child: Path, parent: Path) -> bool:
    try:
        child_real = Path(os.path.realpath(child))
        parent_real = Path(os.path.realpath(parent))
        child_real.relative_to(parent_real)
        return True
    except (ValueError, OSError):
        return False


def _clean_wheel_env(base: dict[str, str]) -> dict[str, str]:
    clean = {key: value for key, value in base.items() if not key.startswith("SPELL_SYNC")}
    for key in _WHEEL_ENV_KEYS_TO_CLEAR:
        clean.pop(key, None)
    clean["PYTHONNOUSERSITE"] = "1"
    return clean


def _venv_interpreter_in_venv(executable: Path, venv_dir: Path) -> bool:
    exe = Path(os.path.normpath(str(executable)))
    venv = Path(os.path.normpath(str(venv_dir)))
    for bin_dir in (venv / "bin", venv / "Scripts"):
        bin_norm = Path(os.path.normpath(str(bin_dir)))
        try:
            exe.relative_to(bin_norm)
            return True
        except ValueError:
            continue
    return False


def _validate_wheel_origin_probe(
    probe: dict[str, object],
    *,
    venv_dir: Path,
    checkout_root: Path,
) -> str | None:
    required = (
        "origin",
        "executable",
        "sysPrefix",
        "purelib",
        "platlib",
        "version",
    )
    for key in required:
        if not isinstance(probe.get(key), str) or not str(probe[key]):
            return "compatibility.wheel-origin-failed"

    origin = Path(str(probe["origin"]))
    executable = Path(str(probe["executable"]))
    sys_prefix = Path(str(probe["sysPrefix"]))
    purelib = Path(str(probe["purelib"]))
    platlib = Path(str(probe["platlib"]))
    version = str(probe["version"])
    venv_resolved = venv_dir
    checkout_resolved = checkout_root

    if not Path(os.path.realpath(origin)).is_file():
        return "compatibility.wheel-origin-failed"
    if version != _EXPECTED_VERSION:
        return "compatibility.wheel-version-failed"
    if not (_path_within(origin, purelib) or _path_within(origin, platlib)):
        return "compatibility.wheel-origin-failed"
    if not (_path_within(purelib, venv_resolved) and _path_within(platlib, venv_resolved)):
        return "compatibility.wheel-origin-failed"
    if not _path_within(sys_prefix, venv_resolved):
        return "compatibility.wheel-origin-failed"
    if not _venv_interpreter_in_venv(executable, venv_resolved):
        return "compatibility.wheel-origin-failed"
    if _path_within(origin, checkout_resolved):
        return "compatibility.wheel-origin-failed"
    return None


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


def _wheel_build_invocation(
    host_python: str,
    *,
    project_root: Path,
    outdir: Path,
    work_dir: Path,
) -> tuple[list[str], Path]:
    """Build wheel without cwd ``build/`` artifact shadowing the PyPI ``build`` module."""
    project_arg = str(project_root.resolve())
    out_arg = str(outdir.resolve())
    if shutil.which("uv") and (project_root / "uv.lock").is_file():
        argv = [
            _resolve_uv_executable(),
            "run",
            "--isolated",
            "--with",
            "build",
            "--with",
            "wheel",
            "--with",
            "setuptools>=77",
            "python",
            "-m",
            "build",
            "-w",
            "-n",
            "--outdir",
            out_arg,
            project_arg,
        ]
        return argv, work_dir
    return (
        [
            host_python,
            "-m",
            "build",
            "-w",
            "-n",
            "--outdir",
            out_arg,
            project_arg,
        ],
        work_dir,
    )


def _run_wheel_compatibility(host_python: str) -> tuple[list[dict[str, object]], int, str]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="spell-sync-compat-") as tmp:
        tmp_path = Path(tmp)
        build_dir = tmp_path / "dist"
        build_dir.mkdir()
        venv_dir = tmp_path / "venv"
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        build_argv, build_cwd = _wheel_build_invocation(
            host_python,
            project_root=ROOT,
            outdir=build_dir,
            work_dir=work_dir,
        )
        rc, output = _run(
            build_argv,
            cwd=build_cwd,
            env=_clean_wheel_env(os.environ),
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

        rc, output = _run(
            [host_python, "-m", "venv", str(venv_dir)],
            env=_clean_wheel_env(os.environ),
        )
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
        clean_env = _clean_wheel_env(os.environ)
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

        rc, output = _run(
            [str(venv_py), "-c", _ORIGIN_PROBE_SCRIPT],
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
        try:
            probe = json.loads(output.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return results, 1, "compatibility.wheel-origin-failed"
        if not isinstance(probe, dict):
            return results, 1, "compatibility.wheel-origin-failed"
        origin_failure = _validate_wheel_origin_probe(
            probe,
            venv_dir=venv_dir,
            checkout_root=ROOT,
        )
        if origin_failure is not None:
            return results, 1, origin_failure

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
        if rc != 0 or _EXPECTED_VERSION not in output:
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
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="Label this cell as experimental (non-blocking). Requires --source-only.",
    )
    parser.add_argument(
        "--source-only",
        action="store_true",
        help=(
            "Source checkout probe: run product tests via the current interpreter/"
            "PYTHONPATH without building or installing a wheel. Required for "
            "interpreters outside project.requires-python."
        ),
    )
    args = parser.parse_args(argv)

    mismatch = _verify_runtime_identity(
        platform_arg=args.platform,
        python_version_arg=args.python_version,
    )
    execution_id = f"compatibility:{args.platform}-py{args.python_version.replace('.', '')}"
    if args.experimental:
        execution_id += "-experimental"
    if args.source_only:
        execution_id += "-source-only"

    def _emit_failure(failed_id: str, *, exit_code: int = 1) -> int:
        payload = {
            "executionId": execution_id,
            "platform": args.platform,
            "pythonVersion": args.python_version,
            "actualPlatform": _actual_platform(),
            "actualPythonVersion": _actual_python_version(),
            "experimental": args.experimental,
            "sourceOnly": args.source_only,
            "exitCode": exit_code,
            "failedId": failed_id,
            "steps": [],
        }
        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"COMPATIBILITY_FAILED_ID={failed_id}")
            print("COMPATIBILITY_RESULT=failed")
            print(f"COMPATIBILITY_EXIT={exit_code}")
        return exit_code

    if mismatch is not None:
        return _emit_failure(mismatch)

    if args.experimental and not args.source_only:
        return _emit_failure("compatibility.experimental-requires-source-only")
    if args.source_only and not args.experimental:
        return _emit_failure("compatibility.source-only-requires-experimental")

    py = sys.executable
    uv = _resolve_uv_executable()
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
            [py, "-m", "pytest", "tests/test_edge_cases.py", "-q"],
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
        if args.source_only:
            results.append(
                {
                    "step": "compatibility.wheel-skipped-source-only",
                    "exitCode": 0,
                    "outputLines": 0,
                }
            )
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
        "sourceOnly": args.source_only,
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
