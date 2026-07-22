#!/usr/bin/env python3
"""Validate support matrix documentation and GitHub Actions CI architecture."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_DOC = ROOT / "docs" / "SUPPORTED_ENVIRONMENTS.md"
CONTRACT_PATH = ROOT / "config" / "environment-contract.toml"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

REQUIRED_DOC_SECTIONS = (
    "## Product Python",
    "## Product platforms",
    "## Maintainer tooling",
    "## Upgrade policies",
)

CANONICAL_JOB_MARKERS = (
    "ubuntu-latest",
    "3.12",
    "scripts/ci.sh",
)

COMPATIBILITY_EXPECTATIONS = (
    ("ubuntu-latest", "3.11"),
    ("macos-latest", "3.12"),
    ("windows-latest", "3.12"),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_files() -> list[Path]:
    if not WORKFLOWS_DIR.is_dir():
        return []
    return sorted(path for path in WORKFLOWS_DIR.glob("*.yml") if path.is_file())


def _job_blocks(text: str) -> dict[str, str]:
    jobs_section = text.split("jobs:", 1)
    if len(jobs_section) < 2:
        return {}
    body = jobs_section[1]
    blocks: dict[str, str] = {}
    for match in re.finditer(r"^  ([A-Za-z0-9_-]+):\n", body, flags=re.MULTILINE):
        name = match.group(1)
        start = match.end()
        next_match = re.search(r"^  [A-Za-z0-9_-]+:\n", body[start:], flags=re.MULTILINE)
        end = start + next_match.start() if next_match else len(body)
        blocks[name] = body[start:end]
    return blocks


def _job_runs_on(block: str) -> str:
    match = re.search(r"^\s*runs-on:\s*(.+)$", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _job_python_versions(block: str) -> set[str]:
    versions: set[str] = set()
    for match in re.finditer(
        r"python-version:\s*(\$\{\{\s*matrix\.python-version\s*\}\}|\"[^\"]+\"|'[^']+')",
        block,
    ):
        token = match.group(1).strip().strip("\"'")
        if token.startswith("${{"):
            for literal in re.findall(r'"(\d+\.\d+)"', block):
                versions.add(literal)
        else:
            versions.add(token)
    for match in re.finditer(r"--python\s+(\d+\.\d+(?:\.\d+)?)", block):
        versions.add(match.group(1))
    return versions


def _job_runs_full_ci(block: str) -> bool:
    return "scripts/ci.sh" in block or "scripts/ci_runner.py" in block


def _job_runs_compatibility_runner(block: str) -> bool:
    return "run_compatibility_checks.py" in block


def _check_support_doc() -> list[str]:
    errors: list[str] = []
    if not SUPPORT_DOC.is_file():
        errors.append(
            "[SUPPORT-MATRIX-010] missing docs/SUPPORTED_ENVIRONMENTS.md; "
            "remediation: document product and maintainer support separately"
        )
        return errors
    text = _read(SUPPORT_DOC)
    for section in REQUIRED_DOC_SECTIONS:
        if section not in text:
            errors.append(
                f"[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md missing section {section}; "
                "remediation: add required support sections"
            )
    for token in (">=3.11", "3.12.13", "3.11", "3.12", "3.13"):
        if token not in text:
            errors.append(
                f"[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must mention Python {token}; "
                "remediation: align product/tooling Python support with environment contract"
            )
    if (
        "Product runtime does **not** require `uv`." not in text
        and "does not require `uv`" not in text
    ):
        errors.append(
            "[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must state product runtime "
            "does not require uv; remediation: separate product and maintainer tooling"
        )
    return errors


def _check_contract_doc_alignment() -> list[str]:
    errors: list[str] = []
    if not CONTRACT_PATH.is_file() or not SUPPORT_DOC.is_file():
        return errors
    contract = tomllib.loads(_read(CONTRACT_PATH))
    doc = _read(SUPPORT_DOC)
    product = contract.get("product", {})
    maintainer = contract.get("maintainer", {})
    compatibility = contract.get("compatibility", {})
    if isinstance(product, dict):
        requirement = str(product.get("pythonRequirement", "")).strip()
        if requirement and requirement not in doc:
            errors.append(
                "[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must match "
                f"product pythonRequirement ({requirement}); remediation: update support doc"
            )
    if isinstance(maintainer, dict):
        canonical = str(maintainer.get("canonicalPython", "")).strip()
        if canonical and canonical not in doc:
            errors.append(
                "[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must mention canonical "
                f"maintainer Python {canonical}; remediation: update support doc"
            )
    if isinstance(compatibility, dict):
        blocking = compatibility.get("blockingPython", [])
        if isinstance(blocking, list):
            for item in blocking:
                if str(item) not in doc:
                    errors.append(
                        "[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must mention blocking "
                        f"Python {item}; remediation: update compatibility section"
                    )
        experimental = compatibility.get("experimentalPython", [])
        if isinstance(experimental, list):
            for item in experimental:
                if str(item) not in doc:
                    errors.append(
                        "[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must mention "
                        f"experimental Python {item}; remediation: update compatibility section"
                    )
    return errors


def _check_workflows() -> list[str]:
    errors: list[str] = []
    workflow_files = _workflow_files()
    if not workflow_files:
        errors.append(
            "[CI-ENVIRONMENT-011] missing .github/workflows CI definitions; "
            "remediation: add canonical and compatibility workflow jobs"
        )
        return errors

    all_jobs: dict[str, tuple[str, str]] = {}
    for path in workflow_files:
        text = _read(path)
        for name, block in _job_blocks(text).items():
            all_jobs[f"{path.name}:{name}"] = (text, block)

    canonical_jobs = [
        key
        for key, (_, block) in all_jobs.items()
        if _job_runs_full_ci(block)
        and "ubuntu-latest" in _job_runs_on(block)
        and "3.12" in _job_python_versions(block)
        and "matrix:" not in block.split("runs-on:", 1)[0]
    ]
    if len(canonical_jobs) != 1:
        errors.append(
            "[CI-ENVIRONMENT-011] expected exactly one canonical Ubuntu Python 3.12 full CI job; "
            f"found {len(canonical_jobs)}; remediation: split canonical full gate from matrix jobs"
        )

    matrix_full_ci_jobs = [
        key
        for key, (_, block) in all_jobs.items()
        if _job_runs_full_ci(block) and "matrix:" in block
    ]
    if matrix_full_ci_jobs:
        errors.append(
            "[CI-ENVIRONMENT-011] full CI must not run inside a compatibility matrix; "
            f"offending jobs: {', '.join(matrix_full_ci_jobs)}; "
            "remediation: keep one canonical full job and narrow compatibility jobs"
        )

    compatibility_jobs = [
        key
        for key, (_, block) in all_jobs.items()
        if _job_runs_compatibility_runner(block)
        or (not _job_runs_full_ci(block) and "matrix:" in block)
    ]
    for os_name, python_version in COMPATIBILITY_EXPECTATIONS:
        matched = False
        for _, block in (all_jobs[key] for key in compatibility_jobs if key in all_jobs):
            if os_name in _job_runs_on(block) and python_version in _job_python_versions(block):
                matched = True
                if _job_runs_full_ci(block):
                    errors.append(
                        f"[CI-ENVIRONMENT-011] compatibility job {os_name} Python "
                        f"{python_version} must not run full CI; remediation: use "
                        "scripts/run_compatibility_checks.py"
                    )
                break
        if not matched:
            errors.append(
                "[CI-ENVIRONMENT-011] missing compatibility job for "
                f"{os_name} Python {python_version}; remediation: add narrow compatibility job"
            )

    experimental_jobs = [
        key
        for key, (text, block) in all_jobs.items()
        if "ubuntu-latest" in _job_runs_on(block) and "3.13" in _job_python_versions(block)
    ]
    if len(experimental_jobs) != 1:
        errors.append(
            "[CI-ENVIRONMENT-011] expected exactly one Ubuntu Python 3.13 experimental job; "
            f"found {len(experimental_jobs)}; remediation: add non-blocking experimental job"
        )
    else:
        text, block = all_jobs[experimental_jobs[0]]
        if "continue-on-error" not in block and "continue-on-error" not in text:
            errors.append(
                "[CI-ENVIRONMENT-011] Python 3.13 experimental job must be non-blocking; "
                "remediation: set continue-on-error: true"
            )
        if _job_runs_full_ci(block):
            errors.append(
                "[CI-ENVIRONMENT-011] Python 3.13 experimental job must not run full CI; "
                "remediation: run product compatibility subset only"
            )

    combined = "\n".join(_read(path) for path in workflow_files)
    if "astral-sh/setup-uv" not in combined and "setup-uv" not in combined:
        errors.append(
            "[CI-ENVIRONMENT-011] workflows must pin uv via setup-uv action; "
            "remediation: add pinned astral-sh/setup-uv step"
        )
    if re.search(r"setup-uv[^\n]*\n[^\n]*version:\s*latest", combined):
        errors.append(
            "[CI-ENVIRONMENT-011] workflows must not use floating latest uv version; "
            "remediation: pin exact tested uv version"
        )
    if "uv.lock" not in combined:
        errors.append(
            "[CI-ENVIRONMENT-011] workflows must reference uv.lock in setup/cache; "
            "remediation: include lock digest in CI bootstrap and cache keys"
        )
    if "--no-python-downloads" not in combined:
        errors.append(
            "[CI-ENVIRONMENT-011] workflows must pass --no-python-downloads to uv commands; "
            "remediation: forbid implicit Python downloads in CI"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_support_doc())
    errors.extend(_check_contract_doc_alignment())
    errors.extend(_check_workflows())

    if errors:
        for item in errors:
            print(item)
        print(f"SUPPORT_MATRIX_VALIDATION=failed checks={len(errors)}")
        return 1
    print("SUPPORT_MATRIX_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
