#!/usr/bin/env python3
"""Project environment lifecycle: bootstrap, sync, check, and metadata."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.environment_contract.contract import (  # noqa: E402
    CANONICAL_PYTHON,
    contract_digest,
    file_digest,
    load_contract,
)
from scripts.environment_contract.fingerprint import build_environment_fingerprint  # noqa: E402
from scripts.environment_contract.manifest import (  # noqa: E402
    build_installed_manifest,
    current_python_cache_tag,
    manifest_digest,
)
from scripts.environment_contract.metadata import (  # noqa: E402
    EnvironmentMetadata,
    metadata_now,
    read_environment_metadata,
    write_environment_metadata,
)

DEFAULT_GROUPS = ("dev",)
UV_VERSION_PATTERN = re.compile(r"uv\s+(\d+\.\d+\.\d+)")


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    failed_id: str = ""
    message: str = ""


def _run(
    command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
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


def _uv_version() -> str:
    code, output = _run(["uv", "--version"])
    if code != 0:
        return ""
    match = UV_VERSION_PATTERN.search(output)
    return match.group(1) if match else ""


def _venv_python(venv_dir: Path) -> Path | None:
    for name in ("python", "python3", "python3.12"):
        candidate = venv_dir / "bin" / name
        if candidate.is_file():
            return candidate
    candidate = venv_dir / "Scripts" / "python.exe"
    if candidate.is_file():
        return candidate
    return None


def _interpreter_identity(python: Path) -> str:
    code, output = _run(
        [
            str(python),
            "-c",
            "import hashlib, platform, sys; "
            "payload=("
            "f'{sys.executable}|{platform.python_version()}|{sys.implementation.cache_tag}'"
            "); "
            "print(hashlib.sha256(payload.encode()).hexdigest())",
        ]
    )
    if code != 0:
        return ""
    return output.splitlines()[-1].strip()


def _python_version(python: Path) -> str:
    code, output = _run([str(python), "-c", "import platform; print(platform.python_version())"])
    if code != 0:
        return ""
    return output.strip()


def _sync_command(*, allow_python_download: bool) -> list[str]:
    command = [
        "uv",
        "sync",
        "--python",
        CANONICAL_PYTHON,
        "--locked",
        "--group",
        "dev",
    ]
    if not allow_python_download:
        command.append("--no-python-downloads")
    return command


def _write_environment_evidence(root: Path, *, check_exit: int, lock_exit: int) -> None:
    fingerprint = build_environment_fingerprint(root, uv_version=_uv_version())
    payload = {
        "schemaVersion": 1,
        "repositoryHead": _git_head(root),
        "environmentContractDigest": fingerprint.environment_contract_digest,
        "pyprojectDigest": fingerprint.pyproject_digest,
        "uvLockDigest": fingerprint.uv_lock_digest,
        "pythonImplementation": fingerprint.python_implementation,
        "pythonVersion": fingerprint.python_version,
        "pythonCacheTag": fingerprint.python_cache_tag,
        "uvVersion": fingerprint.uv_version,
        "pytestVersion": fingerprint.pytest_version,
        "selectedDependencyGroups": list(fingerprint.selected_dependency_groups),
        "installedEnvironmentDigest": fingerprint.installed_environment_digest,
        "environmentCheckExit": check_exit,
        "lockCheckExit": lock_exit,
    }
    out = root / ".artifacts" / "environment" / "environment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _write_metadata(root: Path, venv_dir: Path) -> None:
    python = _venv_python(venv_dir)
    if python is None:
        raise RuntimeError("environment.venv-missing")
    manifest = build_installed_manifest(project_root=root, python=python)
    metadata = EnvironmentMetadata(
        schema_version=1,
        created_at=metadata_now(),
        python_implementation=platform.python_implementation().lower(),
        python_version=_python_version(python),
        python_cache_tag=current_python_cache_tag(),
        base_interpreter_identity=_interpreter_identity(python),
        uv_version=_uv_version(),
        environment_contract_digest=contract_digest(root),
        pyproject_digest=file_digest(root / "pyproject.toml"),
        uv_lock_digest=file_digest(root / "uv.lock"),
        selected_dependency_groups=DEFAULT_GROUPS,
        installed_environment_digest=manifest_digest(manifest),
    )
    write_environment_metadata(venv_dir / ".spell-sync-environment.json", metadata)


def cmd_info(root: Path, *, json_output: bool) -> int:
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    metadata = read_environment_metadata(venv_dir / ".spell-sync-environment.json")
    payload = {
        "environmentContractDigest": contract_digest(root),
        "pyprojectDigest": file_digest(root / "pyproject.toml"),
        "uvLockDigest": file_digest(root / "uv.lock") if (root / "uv.lock").is_file() else "",
        "pythonVersionFile": CANONICAL_PYTHON,
        "uvVersion": _uv_version(),
        "venvPresent": venv_dir.is_dir(),
        "venvPythonVersion": _python_version(_venv_python(venv_dir))
        if _venv_python(venv_dir)
        else "",
        "metadataPresent": metadata is not None,
        "installedEnvironmentDigest": metadata.installed_environment_digest if metadata else "",
        "selectedDependencyGroups": list(DEFAULT_GROUPS),
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}={value}")
    print("ENVIRONMENT_RESULT=success")
    return 0


def cmd_check(root: Path) -> CommandResult:
    contract = load_contract(root)
    if contract.canonical_python != CANONICAL_PYTHON:
        return CommandResult(1, "environment.contract-invalid", "canonical python mismatch")
    required_uv = contract.uv_required_version
    actual_uv = _uv_version()
    if not actual_uv.startswith(required_uv):
        return CommandResult(
            1, "environment.uv-mismatch", f"expected uv {required_uv}, got {actual_uv}"
        )
    lock_path = root / "uv.lock"
    if not lock_path.is_file():
        return CommandResult(1, "environment.lock-missing", "uv.lock missing")
    code, _ = _run(["uv", "lock", "--check"], cwd=root)
    if code != 0:
        return CommandResult(1, "environment.lock-stale", "uv lock check failed")
    venv_dir = root / contract.environment_directory
    if not venv_dir.is_dir():
        return CommandResult(1, "environment.venv-missing", ".venv missing")
    venv_python = _venv_python(venv_dir)
    if venv_python is None:
        return CommandResult(1, "environment.venv-missing", ".venv python missing")
    if _python_version(venv_python) != CANONICAL_PYTHON:
        return CommandResult(1, "environment.venv-python-mismatch", "venv python version mismatch")
    metadata_path = venv_dir / ".spell-sync-environment.json"
    metadata = read_environment_metadata(metadata_path)
    if metadata is None:
        return CommandResult(1, "environment.venv-stale", "environment metadata missing")
    if metadata.uv_lock_digest != file_digest(lock_path):
        return CommandResult(1, "environment.venv-stale", "lock digest mismatch")
    if metadata.environment_contract_digest != contract_digest(root):
        return CommandResult(1, "environment.venv-stale", "contract digest mismatch")
    manifest = build_installed_manifest(project_root=root, python=venv_python)
    if manifest_digest(manifest) != metadata.installed_environment_digest:
        return CommandResult(1, "environment.dependencies-mismatch", "installed manifest mismatch")
    code, _ = _run([str(venv_python), "-m", "pytest", "--version"])
    if code != 0:
        return CommandResult(1, "environment.dependencies-mismatch", "pytest unavailable")
    return CommandResult(0)


def cmd_sync(root: Path, *, allow_python_download: bool = False) -> CommandResult:
    code, output = _run(_sync_command(allow_python_download=allow_python_download), cwd=root)
    if code != 0:
        return CommandResult(code, "environment.sync-required", output)
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    try:
        _write_metadata(root, venv_dir)
    except RuntimeError as exc:
        return CommandResult(1, str(exc), str(exc))
    check = cmd_check(root)
    _write_environment_evidence(root, check_exit=check.exit_code, lock_exit=0)
    if check.exit_code != 0:
        return check
    return CommandResult(0)


def cmd_bootstrap(root: Path, *, allow_python_download: bool) -> CommandResult:
    if not allow_python_download:
        return CommandResult(
            1,
            "environment.python-mismatch",
            "bootstrap requires --allow-python-download",
        )
    code, output = _run(["uv", "python", "install", CANONICAL_PYTHON], cwd=root)
    if code != 0:
        return CommandResult(code, "environment.python-mismatch", output)
    return cmd_sync(root, allow_python_download=False)


def cmd_recreate(root: Path) -> CommandResult:
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    if venv_dir.is_dir():
        import shutil

        shutil.rmtree(venv_dir)
    return cmd_sync(root)


def cmd_clean(root: Path) -> CommandResult:
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    if venv_dir.is_dir():
        import shutil

        shutil.rmtree(venv_dir)
    env_artifacts = root / ".artifacts" / "environment"
    if env_artifacts.is_dir():
        import shutil

        shutil.rmtree(env_artifacts)
    return CommandResult(0)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage spell-sync project environment.")
    parser.add_argument("--json", action="store_true", help="JSON output for info")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    sub.add_parser("check")
    sub.add_parser("sync")
    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--allow-python-download", action="store_true")
    sub.add_parser("recreate")
    sub.add_parser("clean")
    sub.add_parser("installed-manifest")
    sub.add_parser("write-metadata")
    sub.add_parser("doctor")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command == "info":
        return cmd_info(ROOT, json_output=args.json)
    if command == "check":
        result = cmd_check(ROOT)
    elif command == "sync":
        result = cmd_sync(ROOT)
    elif command == "bootstrap":
        result = cmd_bootstrap(ROOT, allow_python_download=args.allow_python_download)
    elif command == "recreate":
        result = cmd_recreate(ROOT)
    elif command == "clean":
        result = cmd_clean(ROOT)
    elif command == "installed-manifest":
        manifest = build_installed_manifest(project_root=ROOT)
        print(json.dumps(manifest.to_json_dict(), indent=2, sort_keys=True))
        print("ENVIRONMENT_RESULT=success")
        return 0
    elif command == "write-metadata":
        contract = load_contract(ROOT)
        _write_metadata(ROOT, ROOT / contract.environment_directory)
        print("ENVIRONMENT_RESULT=success")
        return 0
    elif command == "doctor":
        result = cmd_check(ROOT)
        if result.exit_code == 0:
            print("ENVIRONMENT_DOCTOR=success")
            return 0
        print("ENVIRONMENT_DOCTOR=failed")
    else:
        return 2
    if result.exit_code == 0:
        print("ENVIRONMENT_RESULT=success")
        return 0
    print("ENVIRONMENT_RESULT=failed")
    print(f"ENVIRONMENT_FAILED_ID={result.failed_id}")
    if result.message:
        print(result.message, file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
