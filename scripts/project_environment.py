#!/usr/bin/env python3
"""Project environment lifecycle: bootstrap, sync, check, and metadata."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
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
from scripts.environment_contract.evidence import write_environment_evidence  # noqa: E402
from scripts.environment_contract.fingerprint import (  # noqa: E402
    build_environment_fingerprint_from_probe,
    resolve_project_environment_fingerprint,
)
from scripts.environment_contract.manifest import manifest_digest  # noqa: E402
from scripts.environment_contract.metadata import (  # noqa: E402
    EnvironmentMetadata,
    metadata_now,
    read_environment_metadata,
    write_environment_metadata,
)
from scripts.environment_contract.probe import run_interpreter_probe, venv_python  # noqa: E402

DEFAULT_GROUPS = ("dev",)
FULL_CI_GROUPS = ("dev", "packaging", "release-check")
COMPATIBILITY_GROUPS = ("test-core", "packaging")
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


def _sync_command(*, allow_python_download: bool, groups: tuple[str, ...]) -> list[str]:
    command = [
        "uv",
        "sync",
        "--python",
        CANONICAL_PYTHON,
        "--locked",
    ]
    if groups != DEFAULT_GROUPS:
        command.append("--no-default-groups")
    for group in groups:
        command.extend(["--group", group])
    if not allow_python_download:
        command.append("--no-python-downloads")
    return command


def _git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _expected_metadata(
    root: Path, probe, *, uv_version: str, groups: tuple[str, ...] = DEFAULT_GROUPS
) -> EnvironmentMetadata:
    fingerprint = build_environment_fingerprint_from_probe(
        root,
        probe,
        uv_version=uv_version,
        selected_groups=groups,
    )
    return EnvironmentMetadata(
        schema_version=1,
        created_at="",
        python_implementation=probe.python_implementation,
        python_version=probe.python_version,
        python_cache_tag=probe.python_cache_tag,
        base_interpreter_identity=probe.base_prefix_identity,
        uv_version=uv_version,
        environment_contract_digest=fingerprint.environment_contract_digest,
        pyproject_digest=fingerprint.pyproject_digest,
        uv_lock_digest=fingerprint.uv_lock_digest,
        selected_dependency_groups=groups,
        installed_environment_digest=probe.installed_environment_digest,
    )


def _write_metadata(
    root: Path, venv_dir: Path, probe, *, groups: tuple[str, ...] = DEFAULT_GROUPS
) -> None:
    metadata = _expected_metadata(root, probe, uv_version=_uv_version(), groups=groups)
    metadata = EnvironmentMetadata(
        schema_version=metadata.schema_version,
        created_at=metadata_now(),
        python_implementation=metadata.python_implementation,
        python_version=metadata.python_version,
        python_cache_tag=metadata.python_cache_tag,
        base_interpreter_identity=metadata.base_interpreter_identity,
        uv_version=metadata.uv_version,
        environment_contract_digest=metadata.environment_contract_digest,
        pyproject_digest=metadata.pyproject_digest,
        uv_lock_digest=metadata.uv_lock_digest,
        selected_dependency_groups=metadata.selected_dependency_groups,
        installed_environment_digest=metadata.installed_environment_digest,
    )
    write_environment_metadata(venv_dir / ".spell-sync-environment.json", metadata)


def cmd_info(root: Path, *, json_output: bool) -> int:
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    metadata = read_environment_metadata(venv_dir / ".spell-sync-environment.json")
    fingerprint = resolve_project_environment_fingerprint(root, uv_version=_uv_version())
    payload = {
        "environmentContractDigest": contract_digest(root),
        "pyprojectDigest": file_digest(root / "pyproject.toml"),
        "uvLockDigest": file_digest(root / "uv.lock") if (root / "uv.lock").is_file() else "",
        "pythonVersionFile": CANONICAL_PYTHON,
        "uvVersion": _uv_version(),
        "venvPresent": venv_dir.is_dir(),
        "venvPythonVersion": fingerprint.python_version if fingerprint else "",
        "metadataPresent": metadata is not None,
        "installedEnvironmentDigest": metadata.installed_environment_digest if metadata else "",
        "selectedDependencyGroups": list(metadata.selected_dependency_groups)
        if metadata
        else list(DEFAULT_GROUPS),
        "environmentFingerprint": fingerprint.signature() if fingerprint else "",
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
    venv_py = venv_python(venv_dir)
    if venv_py is None:
        return CommandResult(1, "environment.venv-missing", ".venv python missing")
    try:
        probe = run_interpreter_probe(venv_py, project_root=root)
    except RuntimeError:
        return CommandResult(1, "environment.venv-stale", "interpreter probe failed")
    if probe.python_version != CANONICAL_PYTHON:
        return CommandResult(1, "environment.venv-python-mismatch", "venv python version mismatch")
    metadata_path = venv_dir / ".spell-sync-environment.json"
    metadata = read_environment_metadata(metadata_path)
    if metadata is None:
        return CommandResult(1, "environment.venv-stale", "environment metadata missing")
    expected = _expected_metadata(
        root,
        probe,
        uv_version=actual_uv,
        groups=metadata.selected_dependency_groups,
    )
    declaration_fields = (
        ("schemaVersion", metadata.schema_version, expected.schema_version),
        (
            "environmentContractDigest",
            metadata.environment_contract_digest,
            expected.environment_contract_digest,
        ),
        ("pyprojectDigest", metadata.pyproject_digest, expected.pyproject_digest),
        ("uvLockDigest", metadata.uv_lock_digest, expected.uv_lock_digest),
        ("uvVersion", metadata.uv_version, expected.uv_version),
        (
            "selectedDependencyGroups",
            metadata.selected_dependency_groups,
            expected.selected_dependency_groups,
        ),
        (
            "pythonImplementation",
            metadata.python_implementation,
            expected.python_implementation,
        ),
        ("pythonVersion", metadata.python_version, expected.python_version),
        ("pythonCacheTag", metadata.python_cache_tag, expected.python_cache_tag),
        (
            "baseInterpreterIdentity",
            metadata.base_interpreter_identity,
            expected.base_interpreter_identity,
        ),
    )
    for name, actual, wanted in declaration_fields:
        if actual != wanted:
            return CommandResult(1, "environment.venv-stale", f"{name} mismatch")
    if metadata.installed_environment_digest != expected.installed_environment_digest:
        return CommandResult(
            1,
            "environment.manual-mutation-detected",
            "installed manifest mismatch",
        )
    if manifest_digest(probe.installed_manifest) != metadata.installed_environment_digest:
        return CommandResult(
            1,
            "environment.manual-mutation-detected",
            "installed manifest mismatch",
        )
    code, _ = _run([str(venv_py), "-m", "pytest", "--version"])
    if code != 0:
        return CommandResult(1, "environment.dependencies-mismatch", "pytest unavailable")
    return CommandResult(0)


def cmd_sync(
    root: Path, *, allow_python_download: bool = False, groups: tuple[str, ...] = DEFAULT_GROUPS
) -> CommandResult:
    lock_code, lock_out = _run(["uv", "lock", "--check"], cwd=root)
    if lock_code != 0:
        return CommandResult(lock_code, "environment.lock-stale", lock_out)
    code, output = _run(
        _sync_command(allow_python_download=allow_python_download, groups=groups),
        cwd=root,
    )
    if code != 0:
        return CommandResult(code, "environment.sync-required", output)
    contract = load_contract(root)
    venv_dir = root / contract.environment_directory
    venv_py = venv_python(venv_dir)
    if venv_py is None:
        return CommandResult(1, "environment.venv-missing", ".venv python missing after sync")
    try:
        probe = run_interpreter_probe(venv_py, project_root=root)
        _write_metadata(root, venv_dir, probe, groups=groups)
    except RuntimeError as exc:
        return CommandResult(1, "environment.venv-stale", str(exc))
    check = cmd_check(root)
    fingerprint = resolve_project_environment_fingerprint(root, uv_version=_uv_version())
    if fingerprint is not None:
        write_environment_evidence(
            root,
            fingerprint=fingerprint,
            repository_head=_git_head(root),
            check_exit=check.exit_code,
            lock_exit=lock_code,
        )
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


def _resolve_sync_groups(profile: str | None) -> tuple[str, ...]:
    if profile in {None, "", "contributor"}:
        return DEFAULT_GROUPS
    if profile == "full-ci":
        return FULL_CI_GROUPS
    if profile == "compatibility":
        return COMPATIBILITY_GROUPS
    raise ValueError(f"unknown sync profile: {profile}")


def cmd_dependency_report(root: Path, *, json_output: bool) -> int:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    runtime = [str(item) for item in project.get("dependencies", [])]
    groups = {
        str(name): list(body) for name, body in pyproject.get("dependency-groups", {}).items()
    }
    group_exports: dict[str, object] = {}
    for group_name in sorted(groups):
        code, output = _run(
            ["uv", "export", "--group", group_name, "--no-hashes", "--no-emit-project"],
            cwd=root,
        )
        packages: list[str] = []
        if code == 0:
            for line in output.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    packages.append(stripped.split("==")[0].split("[")[0])
        group_exports[group_name] = {
            "directDeclarations": len(groups[group_name]),
            "resolvedPackageCount": len(set(packages)),
        }
    payload = {
        "directRuntimeDependencies": runtime,
        "dependencyGroups": sorted(groups),
        "groupExports": group_exports,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"directRuntimeDependencies={len(runtime)}")
        for group_name in sorted(groups):
            export = group_exports[group_name]
            assert isinstance(export, dict)
            print(
                f"group:{group_name}="
                f"direct={export['directDeclarations']} "
                f"resolved={export['resolvedPackageCount']}"
            )
    print("DEPENDENCY_REPORT_RESULT=success")
    return 0


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
    sync = sub.add_parser("sync")
    sync.add_argument(
        "--profile",
        choices=("contributor", "full-ci", "compatibility"),
        default="contributor",
        help="contributor=dev; full-ci adds packaging and release-check",
    )
    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--allow-python-download", action="store_true")
    sub.add_parser("recreate")
    sub.add_parser("clean")
    sub.add_parser("dependency-report")
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
        try:
            groups = _resolve_sync_groups(getattr(args, "profile", "contributor"))
        except ValueError as exc:
            print("ENVIRONMENT_RESULT=failed")
            print("ENVIRONMENT_FAILED_ID=environment.profile-invalid")
            print(str(exc), file=sys.stderr)
            return 1
        result = cmd_sync(ROOT, groups=groups)
    elif command == "dependency-report":
        return cmd_dependency_report(ROOT, json_output=args.json)
    elif command == "bootstrap":
        result = cmd_bootstrap(ROOT, allow_python_download=args.allow_python_download)
    elif command == "recreate":
        result = cmd_recreate(ROOT)
    elif command == "clean":
        result = cmd_clean(ROOT)
    elif command == "installed-manifest":
        contract = load_contract(ROOT)
        venv_py = venv_python(ROOT / contract.environment_directory)
        if venv_py is None:
            print("ENVIRONMENT_RESULT=failed")
            print("ENVIRONMENT_FAILED_ID=environment.venv-missing")
            return 1
        probe = run_interpreter_probe(venv_py, project_root=ROOT)
        print(json.dumps(probe.installed_manifest.to_json_dict(), indent=2, sort_keys=True))
        print("ENVIRONMENT_RESULT=success")
        return 0
    elif command == "write-metadata":
        contract = load_contract(ROOT)
        venv_dir = ROOT / contract.environment_directory
        venv_py = venv_python(venv_dir)
        if venv_py is None:
            print("ENVIRONMENT_RESULT=failed")
            print("ENVIRONMENT_FAILED_ID=environment.venv-missing")
            return 1
        probe = run_interpreter_probe(venv_py, project_root=ROOT)
        _write_metadata(ROOT, venv_dir, probe)
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
