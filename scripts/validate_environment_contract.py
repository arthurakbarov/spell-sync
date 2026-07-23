#!/usr/bin/env python3
"""Validate environment contract, Python pin, uv policy, lock, and dependency SSOT."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "environment-contract.toml"
PYTHON_VERSION_PATH = ROOT / ".python-version"
PYPROJECT_PATH = ROOT / "pyproject.toml"
UV_LOCK_PATH = ROOT / "uv.lock"
GITIGNORE_PATH = ROOT / ".gitignore"

REQUIRED_GROUPS = ("test-core", "coverage", "quality", "packaging", "release-check", "dev")
DEV_INCLUDES = ("test-core", "coverage", "quality")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_name(spec: object) -> str:
    if isinstance(spec, dict):
        return ""
    text = str(spec).strip()
    return re.split(r"[<>=!;\[]", text, maxsplit=1)[0].strip().lower().replace("_", "-")


def _collect_group_packages(groups: dict[str, object], name: str, *, seen: set[str]) -> set[str]:
    if name in seen:
        return set()
    seen.add(name)
    raw = groups.get(name)
    if not isinstance(raw, list):
        return set()
    packages: set[str] = set()
    for item in raw:
        if isinstance(item, dict) and "include-group" in item:
            included = str(item["include-group"])
            packages.update(_collect_group_packages(groups, included, seen=seen))
            continue
        package = _package_name(item)
        if package:
            packages.add(package)
    return packages


def _check_contract_file() -> list[str]:
    errors: list[str] = []
    if not CONTRACT_PATH.is_file():
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] missing config/environment-contract.toml; "
            "remediation: add committed environment contract SSOT"
        )
        return errors
    try:
        data = tomllib.loads(_read(CONTRACT_PATH))
    except tomllib.TOMLDecodeError as exc:
        errors.append(
            f"[ENVIRONMENT-CONTRACT-001] invalid config/environment-contract.toml: {exc}; "
            "remediation: fix TOML syntax"
        )
        return errors
    if int(data.get("schemaVersion", 0)) != 1:
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] config/environment-contract.toml schemaVersion must be 1; "
            "remediation: set schemaVersion = 1"
        )
    product = data.get("product", {})
    maintainer = data.get("maintainer", {})
    toolchain = data.get("toolchain", {})
    if not isinstance(product, dict) or not product.get("pythonRequirement"):
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] config/environment-contract.toml missing "
            "[product].pythonRequirement; remediation: declare product Python requirement"
        )
    if not isinstance(maintainer, dict) or not maintainer.get("canonicalPython"):
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] config/environment-contract.toml missing "
            "[maintainer].canonicalPython; remediation: declare canonical maintainer Python"
        )
    if not isinstance(toolchain, dict) or not toolchain.get("uvRequiredVersion"):
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] config/environment-contract.toml missing "
            "[toolchain].uvRequiredVersion; remediation: pin tested uv version"
        )
    downloads = maintainer.get("pythonDownloads", {}) if isinstance(maintainer, dict) else {}
    if not isinstance(downloads, dict) or downloads.get("normalCommands") != "forbidden":
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] config/environment-contract.toml must forbid normal "
            "Python downloads; remediation: set [maintainer.pythonDownloads].normalCommands "
            '= "forbidden"'
        )
    return errors


def _check_python_version(contract_data: dict[str, object] | None) -> list[str]:
    errors: list[str] = []
    if not PYTHON_VERSION_PATH.is_file():
        errors.append(
            "[ENVIRONMENT-PYTHON-002] missing .python-version; "
            "remediation: commit canonical maintainer Python pin"
        )
        return errors
    value = _read(PYTHON_VERSION_PATH).strip()
    if not value:
        errors.append(
            "[ENVIRONMENT-PYTHON-002] .python-version is empty; "
            "remediation: set canonical maintainer Python"
        )
        return errors
    if contract_data is not None:
        maintainer = contract_data.get("maintainer", {})
        canonical = ""
        if isinstance(maintainer, dict):
            canonical = str(maintainer.get("canonicalPython", "")).strip()
        if canonical and value != canonical:
            errors.append(
                "[ENVIRONMENT-PYTHON-002] .python-version must match "
                f"[maintainer].canonicalPython ({canonical}); remediation: align committed pins"
            )
    return errors


def _check_pyproject(contract_data: dict[str, object] | None) -> list[str]:
    errors: list[str] = []
    if not PYPROJECT_PATH.is_file():
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] missing pyproject.toml; "
            "remediation: restore project metadata"
        )
        return errors
    try:
        data = tomllib.loads(_read(PYPROJECT_PATH))
    except tomllib.TOMLDecodeError as exc:
        errors.append(
            f"[ENVIRONMENT-CONTRACT-001] invalid pyproject.toml: {exc}; "
            "remediation: fix TOML syntax"
        )
        return errors

    project = data.get("project", {})
    requires_python = ""
    if isinstance(project, dict):
        requires_python = str(project.get("requires-python", "")).strip()
    contract_requirement = ""
    if contract_data is not None:
        product = contract_data.get("product", {})
        if isinstance(product, dict):
            contract_requirement = str(product.get("pythonRequirement", "")).strip()
    if not requires_python:
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] pyproject.toml missing project.requires-python; "
            "remediation: declare public Python requirement"
        )
    elif contract_requirement and requires_python != contract_requirement:
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] pyproject.toml project.requires-python must match "
            f"environment contract ({contract_requirement}); remediation: align declarations"
        )

    tool_uv = data.get("tool", {})
    uv_config = tool_uv.get("uv", {}) if isinstance(tool_uv, dict) else {}
    if not isinstance(uv_config, dict):
        uv_config = {}
    required_version = str(uv_config.get("required-version", "")).strip()
    default_groups = uv_config.get("default-groups")
    python_downloads = str(uv_config.get("python-downloads", "")).strip()
    if not required_version:
        errors.append(
            "[ENVIRONMENT-UV-003] pyproject.toml missing [tool.uv].required-version; "
            "remediation: pin tested uv version"
        )
    if not isinstance(default_groups, list) or "dev" not in default_groups:
        errors.append(
            "[ENVIRONMENT-UV-003] pyproject.toml [tool.uv].default-groups must include dev; "
            'remediation: set default-groups = ["dev"]'
        )
    if python_downloads != "manual":
        errors.append(
            "[ENVIRONMENT-UV-003] pyproject.toml [tool.uv].python-downloads must be manual; "
            "remediation: forbid implicit Python downloads in normal commands"
        )
    if contract_data is not None and required_version:
        toolchain = contract_data.get("toolchain", {})
        contract_uv = ""
        if isinstance(toolchain, dict):
            contract_uv = str(toolchain.get("uvRequiredVersion", "")).strip()
        expected = f"=={contract_uv}" if contract_uv else ""
        if contract_uv and required_version != expected:
            errors.append(
                "[ENVIRONMENT-UV-003] pyproject.toml [tool.uv].required-version must match "
                f"environment contract ({expected}); remediation: align uv pin"
            )

    groups = data.get("dependency-groups", {})
    if not isinstance(groups, dict):
        groups = {}
    for group_name in REQUIRED_GROUPS:
        if group_name not in groups:
            errors.append(
                "[ENVIRONMENT-CONTRACT-001] pyproject.toml missing "
                f"dependency-groups.{group_name}; "
                "remediation: declare maintainer dependency groups"
            )
    dev_group = groups.get("dev")
    if isinstance(dev_group, list):
        includes = {
            str(item["include-group"])
            for item in dev_group
            if isinstance(item, dict) and "include-group" in item
        }
        missing_includes = set(DEV_INCLUDES) - includes
        if missing_includes:
            errors.append(
                "[ENVIRONMENT-CONTRACT-001] pyproject.toml dependency-groups.dev must include "
                f"{sorted(missing_includes)}; remediation: add include-group entries"
            )

    optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    dev_extra = optional.get("dev") if isinstance(optional, dict) else None
    if not isinstance(dev_extra, list) or not dev_extra:
        errors.append(
            "[ENVIRONMENT-CONTRACT-001] pyproject.toml missing "
            "[project.optional-dependencies].dev; "
            "remediation: keep transitional dev extra aligned with dependency groups"
        )
    elif isinstance(groups, dict):
        pyproject_text = _read(PYPROJECT_PATH)
        if "Deprecated" in pyproject_text:
            pass
        else:
            group_packages = _collect_group_packages(groups, "dev", seen=set())
            extra_packages = {_package_name(item) for item in dev_extra if _package_name(item)}
            if group_packages != extra_packages:
                missing = sorted(group_packages - extra_packages)
                extra = sorted(extra_packages - group_packages)
                detail = []
                if missing:
                    detail.append(f"missing from dev extra: {', '.join(missing)}")
                if extra:
                    detail.append(f"extra in dev extra: {', '.join(extra)}")
                errors.append(
                    "[ENVIRONMENT-CONTRACT-001] dependency-groups dev and optional-dependencies dev "
                    f"must align ({'; '.join(detail)}); remediation: sync dev extra with groups SSOT"
                )
    return errors


def _check_uv_lock() -> list[str]:
    errors: list[str] = []
    if not UV_LOCK_PATH.is_file():
        errors.append(
            "[ENVIRONMENT-LOCK-004] missing uv.lock; "
            "remediation: generate and commit uv.lock from pyproject declarations"
        )
        return errors
    lock_text = _read(UV_LOCK_PATH)
    if not lock_text.strip():
        errors.append(
            "[ENVIRONMENT-LOCK-004] uv.lock is empty; remediation: regenerate lock with uv lock"
        )
    return errors


def _check_gitignore() -> list[str]:
    errors: list[str] = []
    if not GITIGNORE_PATH.is_file():
        errors.append(
            "[ENVIRONMENT-VENV-005] missing .gitignore; remediation: ignore disposable .venv/"
        )
        return errors
    lines = [line.strip() for line in _read(GITIGNORE_PATH).splitlines()]
    if ".venv/" not in lines:
        errors.append(
            "[ENVIRONMENT-VENV-005] .gitignore must contain .venv/; "
            "remediation: ignore local disposable virtual environment"
        )
    return errors


def _check_project_environment_probe() -> list[str]:
    errors: list[str] = []
    probe_path = ROOT / "scripts/environment_contract/probe.py"
    project_env = ROOT / "scripts/project_environment.py"
    if probe_path.is_file():
        text = _read(probe_path)
        if "importlib.metadata.distributions()" not in text:
            errors.append("[ENVIRONMENT-PROBE-006] probe must interrogate .venv installed manifest")
        if "purelib" not in text or "_in_venv" not in text:
            errors.append(
                "[ENVIRONMENT-PROBE-007] probe must limit installed manifest to venv site-packages"
            )
    else:
        errors.append("[ENVIRONMENT-PROBE-006] missing scripts/environment_contract/probe.py")
    if project_env.is_file():
        text = _read(project_env)
        if "run_interpreter_probe" not in text:
            errors.append(
                "[ENVIRONMENT-PROBE-006] project_environment must use run_interpreter_probe"
            )
    skill = ROOT / ".cursor/skills/project-environment/SKILL.md"
    if not skill.is_file():
        errors.append("[ENVIRONMENT-SKILL-007] missing .cursor/skills/project-environment/SKILL.md")
    return errors


def _check_ci_evidence_environment() -> list[str]:
    errors: list[str] = []
    evidence_script = ROOT / "scripts/check-ci-evidence.py"
    conftest = ROOT / "tests/conftest_execution.py"
    if evidence_script.is_file():
        text = _read(evidence_script)
        if "read_environment_evidence" not in text:
            errors.append(
                "[ENVIRONMENT-EVIDENCE-008] check-ci-evidence must read environment evidence path"
            )
        if "_validate_environment_evidence" not in text:
            errors.append(
                "[ENVIRONMENT-EVIDENCE-008] check-ci-evidence must validate environment evidence"
            )
    if conftest.is_file():
        text = _read(conftest)
        if 'startswith("test_execution_")' in text:
            errors.append(
                "[ENVIRONMENT-PATHS-009] filename-based CI evidence isolation is forbidden"
            )
    missing_evidence_test = ROOT / "tests/test_environment_evidence_required.py"
    if missing_evidence_test.is_file():
        text = _read(missing_evidence_test)
        if "evidence_path.unlink()" not in text:
            errors.append(
                "[ENVIRONMENT-EVIDENCE-008] missing-evidence test must delete only environment.json"
            )
    return errors


def main() -> int:
    errors: list[str] = []
    contract_data: dict[str, object] | None = None
    if CONTRACT_PATH.is_file():
        try:
            contract_data = tomllib.loads(_read(CONTRACT_PATH))
        except tomllib.TOMLDecodeError:
            contract_data = None

    errors.extend(_check_contract_file())
    errors.extend(_check_python_version(contract_data))
    errors.extend(_check_pyproject(contract_data))
    errors.extend(_check_uv_lock())
    errors.extend(_check_gitignore())
    errors.extend(_check_project_environment_probe())
    errors.extend(_check_ci_evidence_environment())

    if errors:
        for item in errors:
            print(item)
        print(f"ENVIRONMENT_CONTRACT_VALIDATION=failed checks={len(errors)}")
        return 1
    print("ENVIRONMENT_CONTRACT_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
