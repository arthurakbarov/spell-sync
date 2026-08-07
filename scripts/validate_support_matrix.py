#!/usr/bin/env python3
"""Validate support matrix documentation and GitHub Actions CI architecture."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_DOC = ROOT / "docs" / "SUPPORTED_ENVIRONMENTS.md"
CONTRACT_PATH = ROOT / "config" / "environment-contract.toml"
PYTHON_VERSION_PATH = ROOT / ".python-version"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

REQUIRED_DOC_SECTIONS = (
    "## Product Python",
    "## Product platforms",
    "## Maintainer tooling",
    "## Upgrade policies",
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
    for token in (">=3.11,<3.13", "3.12.13", "3.11", "3.12", "3.13", "source-only"):
        if token not in text:
            errors.append(
                f"[SUPPORT-MATRIX-010] docs/SUPPORTED_ENVIRONMENTS.md must mention {token}; "
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
        and "3.12.13" in _job_python_versions(block)
        and "matrix:" not in block.split("runs-on:", 1)[0]
    ]
    if len(canonical_jobs) != 1:
        errors.append(
            "[CI-ENVIRONMENT-011] expected exactly one canonical Ubuntu Python "
            "3.12.13 full CI job; "
            f"found {len(canonical_jobs)}; remediation: split canonical full gate from matrix jobs"
        )

    for key, (_, block) in all_jobs.items():
        if _job_runs_full_ci(block) and "ubuntu-latest" in _job_runs_on(block):
            if "project_environment.py sync" not in block:
                errors.append(
                    "[CI-ENVIRONMENT-012] canonical full CI must run project_environment.py sync; "
                    f"job {key} missing canonical environment sync"
                )
            if re.search(r'python-version:\s*"3\.12"\s*$', block, flags=re.MULTILINE):
                errors.append(
                    "[CI-ENVIRONMENT-012] canonical full CI must pin exact Python patch 3.12.13; "
                    f"job {key} uses floating 3.12"
                )
            if "uv sync" in block and "project_environment.py sync" not in block:
                errors.append(
                    "[CI-ENVIRONMENT-012] canonical full CI must not use raw uv sync without "
                    "project_environment metadata; remediation: call project_environment.py sync"
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
            f"found {len(experimental_jobs)}; remediation: add non-blocking source-only probe"
        )
    else:
        text, block = all_jobs[experimental_jobs[0]]
        job_key = experimental_jobs[0]
        errors.extend(
            check_experimental_source_only_job(
                block,
                job_name=job_key,
                python_version="3.13",
            )
        )

    for key, (_, block) in all_jobs.items():
        versions = _job_python_versions(block)
        if not _job_runs_compatibility_runner(block):
            continue
        if "3.13" in versions:
            continue
        errors.extend(check_blocking_job_forbids_source_only(block, job_name=key))

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
    contract = tomllib.loads(_read(CONTRACT_PATH)) if CONTRACT_PATH.is_file() else {}
    maintainer = contract.get("maintainer", {}) if isinstance(contract, dict) else {}
    canonical_python = (
        str(maintainer.get("canonicalPython", "")).strip() if isinstance(maintainer, dict) else ""
    )
    python_version_file = (
        PYTHON_VERSION_PATH.read_text(encoding="utf-8").strip()
        if PYTHON_VERSION_PATH.is_file()
        else ""
    )
    if canonical_python and python_version_file and canonical_python != python_version_file:
        errors.append(
            "[CI-ENVIRONMENT-012] .python-version must match environment contract canonicalPython"
        )
    if canonical_python and canonical_python not in combined:
        errors.append(
            "[CI-ENVIRONMENT-012] workflows must reference exact canonical Python patch "
            f"{canonical_python}"
        )
    return errors


def _check_compatibility_runner() -> list[str]:
    errors: list[str] = []
    script = ROOT / "scripts/run_compatibility_checks.py"
    if not script.is_file():
        return errors
    text = _read(script)
    for marker in (
        "compatibility.wheel-build",
        "compatibility.wheel-venv",
        "compatibility.wheel-install",
        "compatibility.wheel-origin",
        "compatibility.wheel-version",
        "compatibility.wheel-cli",
        "--source-only",
        "sourceOnly",
        "compatibility.wheel-skipped-source-only",
        "compatibility.experimental-requires-source-only",
        "compatibility.source-only-requires-experimental",
    ):
        if marker not in text:
            errors.append(
                f"[COMPATIBILITY-WHEEL-013] run_compatibility_checks.py must include {marker}"
            )
    if "installed-wheel-import" in text:
        errors.append(
            "[COMPATIBILITY-WHEEL-013] run_compatibility_checks.py must not use misleading "
            "installed-wheel-import against editable checkout"
        )
    if "PYTHONPATH" not in text:
        errors.append("[COMPATIBILITY-WHEEL-013] compatibility wheel install must clear PYTHONPATH")
    origin_markers = (
        "sysPrefix",
        "purelib",
        "platlib",
        "_validate_wheel_origin_probe",
        "PYTHONNOUSERSITE",
    )
    for marker in origin_markers:
        if marker not in text:
            errors.append(
                "[COMPATIBILITY-WHEEL-013] run_compatibility_checks.py must "
                f"validate wheel origin using {marker}"
            )
    if "_clean_wheel_env" not in text:
        errors.append(
            "[COMPATIBILITY-WHEEL-013] compatibility wheel workflow must use cleaned subprocess env"
        )
    return errors


def check_experimental_source_only_job(
    block: str,
    *,
    job_name: str,
    python_version: str,
    workflow_text: str = "",
) -> list[str]:
    """Reject experimental jobs that treat out-of-range Pythons as installable.

    Semantic requirements are evaluated **only** against ``block`` (this job body).
    ``workflow_text`` is ignored for token presence so sibling jobs cannot satisfy
    ``--source-only``, ``continue-on-error``, or related flags.

    Limitation: job text comes from a regex YAML splitter and checks are substring
    matches. A comment containing ``--source-only`` can still false-positive; this
    validator does not build a YAML AST.
    """
    del workflow_text  # intentionally unused — do not scan sibling jobs
    errors: list[str] = []
    if "continue-on-error" not in block:
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} must be non-blocking; "
            "remediation: set continue-on-error: true on this job"
        )
    if _job_runs_full_ci(block):
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} must not run full CI; "
            "remediation: run source-only product subset"
        )
    sync_pattern = re.compile(
        rf"uv\s+sync\s+[^\n]*--python\s+{re.escape(python_version)}\b"
    )
    if sync_pattern.search(block):
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} must not run "
            f"project-level `uv sync --python {python_version}` while that version is "
            "outside requires-python; remediation: isolate a probe venv without installing "
            "the project"
        )
    if "run_compatibility_checks.py" not in block:
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} must invoke "
            "scripts/run_compatibility_checks.py; remediation: call the source-only runner"
        )
    else:
        if "--source-only" not in block:
            errors.append(
                f"[CI-ENVIRONMENT-015] experimental job {job_name} must invoke "
                "run_compatibility_checks.py with --source-only; remediation: add --source-only "
                "and skip wheel install"
            )
        if "--experimental" not in block:
            errors.append(
                f"[CI-ENVIRONMENT-015] experimental job {job_name} must invoke "
                "run_compatibility_checks.py with --experimental; remediation: pass both "
                "--experimental and --source-only"
            )
    if "--no-python-downloads" not in block:
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} must pass "
            "--no-python-downloads to uv commands in this job; remediation: forbid implicit "
            "Python downloads (interpreter comes from setup-python)"
        )
    if "source" not in job_name.lower() and "source" not in block.lower():
        errors.append(
            f"[CI-ENVIRONMENT-015] experimental job {job_name} should be labeled as a "
            "source compatibility probe; remediation: rename job/name to include 'source'"
        )
    return errors


def check_blocking_job_forbids_source_only(block: str, *, job_name: str) -> list[str]:
    """Blocking compatibility jobs must keep the wheel install flow."""
    if "--source-only" not in block:
        return []
    return [
        f"[CI-ENVIRONMENT-015] blocking compatibility job {job_name} must not use "
        "--source-only; remediation: reserve source-only for experimental probes"
    ]


def _specifier_includes_version(requires: str, version: str) -> bool | None:
    """Return whether ``version`` satisfies ``requires``, or None if packaging is unavailable."""
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except ImportError:
        return None
    try:
        return Version(version) in SpecifierSet(requires)
    except Exception:
        return None


def check_pyproject_python_alignment(
    *,
    requires_python: str,
    contract_requirement: str,
    blocking: list[str],
    experimental: list[str],
    classifiers: list[str],
) -> list[str]:
    """Public requires-python / classifiers must not claim beyond blocking support."""
    errors: list[str] = []
    requires = requires_python.strip()
    expected = contract_requirement.strip()
    if expected and requires != expected:
        errors.append(
            "[SUPPORT-MATRIX-014] pyproject.toml requires-python must match "
            f"environment-contract product.pythonRequirement ({expected!r}); "
            f"found {requires!r}; remediation: align public install range with contract"
        )
    claimed: list[str] = []
    for item in classifiers:
        text = str(item)
        if text.startswith("Programming Language :: Python :: 3."):
            claimed.append(text.rsplit(" :: ", 1)[-1])
    for version in claimed:
        if version in experimental and version not in blocking:
            errors.append(
                "[SUPPORT-MATRIX-014] pyproject classifiers must not claim experimental "
                f"Python {version} as supported; remediation: keep classifiers to blocking set"
            )
        elif blocking and version not in blocking and version not in experimental:
            errors.append(
                "[SUPPORT-MATRIX-014] pyproject classifier Python "
                f"{version} is outside contract compatibility lists; "
                "remediation: align classifiers with environment-contract.toml"
            )
    for version in blocking:
        marker = f"Programming Language :: Python :: {version}"
        if marker not in classifiers:
            errors.append(
                "[SUPPORT-MATRIX-014] pyproject classifiers missing blocking Python "
                f"{version}; remediation: list each blocking version"
            )
    if experimental and requires and "<" not in requires:
        errors.append(
            "[SUPPORT-MATRIX-014] when experimentalPython is declared, "
            "requires-python must include an upper bound so installers do not treat "
            "experimental runtimes as publicly supported; remediation: constrain "
            "requires-python to the blocking range (e.g. '>=3.11,<3.13')"
        )
    for version in experimental:
        included = _specifier_includes_version(requires, version)
        if included is True:
            errors.append(
                "[SUPPORT-MATRIX-014] requires-python must exclude experimental Python "
                f"{version}; remediation: tighten the public install range "
                "(wheel Requires-Python mirrors project.requires-python; installing the "
                "wheel on experimental interpreters is not an expected success path)"
            )
        elif included is None and requires and f"<{version}" not in requires:
            # Minimal fallback without packaging: require an explicit upper bound token.
            major_minor = version
            next_major = version  # e.g. expect "<3.13" for experimental 3.13
            if f"<{major_minor}" not in requires and f",<{major_minor}" not in requires:
                errors.append(
                    "[SUPPORT-MATRIX-014] requires-python should exclude experimental "
                    f"Python {next_major} via an upper bound (packaging unavailable for "
                    "precise SpecifierSet check); remediation: use e.g. '>=3.11,<3.13'"
                )
    return errors


def _check_pyproject_python_alignment() -> list[str]:
    pyproject_path = ROOT / "pyproject.toml"
    if not CONTRACT_PATH.is_file() or not pyproject_path.is_file():
        return []
    contract = tomllib.loads(_read(CONTRACT_PATH))
    project = tomllib.loads(_read(pyproject_path)).get("project", {})
    if not isinstance(project, dict):
        return []
    requires = str(project.get("requires-python", "")).strip()
    product = contract.get("product", {})
    compatibility = contract.get("compatibility", {})
    expected = ""
    if isinstance(product, dict):
        expected = str(product.get("pythonRequirement", "")).strip()
    blocking: list[str] = []
    experimental: list[str] = []
    if isinstance(compatibility, dict):
        raw_blocking = compatibility.get("blockingPython", [])
        raw_experimental = compatibility.get("experimentalPython", [])
        if isinstance(raw_blocking, list):
            blocking = [str(item) for item in raw_blocking]
        if isinstance(raw_experimental, list):
            experimental = [str(item) for item in raw_experimental]
    classifiers = project.get("classifiers", [])
    if not isinstance(classifiers, list):
        classifiers = []
    return check_pyproject_python_alignment(
        requires_python=requires,
        contract_requirement=expected,
        blocking=blocking,
        experimental=experimental,
        classifiers=[str(item) for item in classifiers],
    )


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_support_doc())
    errors.extend(_check_contract_doc_alignment())
    errors.extend(_check_workflows())
    errors.extend(_check_compatibility_runner())
    errors.extend(_check_pyproject_python_alignment())

    if errors:
        for item in errors:
            print(item)
        print(f"SUPPORT_MATRIX_VALIDATION=failed checks={len(errors)}")
        return 1
    print("SUPPORT_MATRIX_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
