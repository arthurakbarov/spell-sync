"""Negative and positive checks for support-matrix Python policy helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_support_matrix import (  # noqa: E402
    check_blocking_job_forbids_source_only,
    check_experimental_source_only_job,
    check_pyproject_python_alignment,
)


_BLOCKING = ["3.11", "3.12"]
_EXPERIMENTAL = ["3.13"]
_GOOD_CLASSIFIERS = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

_SIBLING_WITH_SOURCE_ONLY = """
jobs:
  other-job:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: echo --source-only --experimental --no-python-downloads
"""


def test_rejects_experimental_classifier() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.11,<3.13",
        contract_requirement=">=3.11,<3.13",
        blocking=_BLOCKING,
        experimental=_EXPERIMENTAL,
        classifiers=[*_GOOD_CLASSIFIERS, "Programming Language :: Python :: 3.13"],
    )
    assert any("must not claim experimental" in item for item in errors)


def test_rejects_missing_blocking_classifier() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.11,<3.13",
        contract_requirement=">=3.11,<3.13",
        blocking=_BLOCKING,
        experimental=_EXPERIMENTAL,
        classifiers=[
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.11",
        ],
    )
    assert any("missing blocking Python 3.12" in item for item in errors)


def test_rejects_contract_requires_python_mismatch() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.11",
        contract_requirement=">=3.11,<3.13",
        blocking=_BLOCKING,
        experimental=_EXPERIMENTAL,
        classifiers=_GOOD_CLASSIFIERS,
    )
    assert any("must match environment-contract" in item for item in errors)


def test_rejects_experimental_without_upper_bound() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.11",
        contract_requirement=">=3.11",
        blocking=_BLOCKING,
        experimental=_EXPERIMENTAL,
        classifiers=_GOOD_CLASSIFIERS,
    )
    assert any("upper bound" in item or "must exclude experimental" in item for item in errors)


def test_rejects_py313_job_with_uv_sync() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv sync --python 3.13 --locked --no-python-downloads
          python scripts/run_compatibility_checks.py --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert any("must not run project-level `uv sync" in item for item in errors)


def test_rejects_py313_runner_without_source_only() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py --platform linux --python-version 3.13 --experimental
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
        workflow_text=_SIBLING_WITH_SOURCE_ONLY,
    )
    assert any("--source-only" in item for item in errors)


def test_rejects_when_source_only_only_in_sibling_job() -> None:
    """Sibling job tokens must not satisfy this job's --source-only requirement."""
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
        workflow_text=_SIBLING_WITH_SOURCE_ONLY,
    )
    assert any("with --source-only" in item for item in errors)


def test_rejects_when_continue_on_error_only_in_sibling_job() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
        workflow_text=_SIBLING_WITH_SOURCE_ONLY,
    )
    assert any("non-blocking" in item or "continue-on-error: true" in item for item in errors)


def test_accepts_continue_on_error_true() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert not any("continue-on-error" in item for item in errors)
    assert errors == []


def test_rejects_continue_on_error_false() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: false
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert any("continue-on-error: true" in item and "false" in item for item in errors)


def test_rejects_missing_continue_on_error() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert any("continue-on-error: true" in item for item in errors)


def test_commented_continue_on_error_true_does_not_count() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    # continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          PYTHONPATH=$PWD .venv-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert any("continue-on-error: true" in item for item in errors)


def test_rejects_experimental_job_without_compatibility_runner() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-probe
          echo probe-without-runner
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
        workflow_text="run_compatibility_checks.py --source-only --experimental",
    )
    assert any("must invoke scripts/run_compatibility_checks.py" in item for item in errors)


def test_rejects_experimental_job_without_no_python_downloads() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project .venv-py313-source-probe
          PYTHONPATH=$PWD .venv-py313-source-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
        workflow_text="uv sync --no-python-downloads",
    )
    assert any("--no-python-downloads" in item for item in errors)


def test_accepts_correct_source_only_job() -> None:
    block = """
    name: source compatibility probe (ubuntu, py3.13)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: |
          uv venv --python 3.13 --no-project --no-python-downloads .venv-py313-source-probe
          PYTHONPATH=$PWD .venv-py313-source-probe/bin/python scripts/run_compatibility_checks.py \\
            --platform linux --python-version 3.13 --experimental --source-only
    """
    errors = check_experimental_source_only_job(
        block,
        job_name="source-compat-linux-py313-experimental",
        python_version="3.13",
    )
    assert errors == []


def test_rejects_source_only_on_blocking_job() -> None:
    block = """
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/run_compatibility_checks.py --platform linux --python-version 3.11 --source-only
    """
    errors = check_blocking_job_forbids_source_only(
        block,
        job_name="compatibility-linux-py311",
    )
    assert any("must not use --source-only" in item for item in errors)


def test_accepts_aligned_blocking_metadata() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.11,<3.13",
        contract_requirement=">=3.11,<3.13",
        blocking=_BLOCKING,
        experimental=_EXPERIMENTAL,
        classifiers=_GOOD_CLASSIFIERS,
    )
    assert errors == []


def test_public_requires_python_excludes_313_for_wheel_metadata() -> None:
    """Wheel Requires-Python mirrors project.requires-python; 3.13 install is not expected."""
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    requires = ">=3.11,<3.13"
    spec = SpecifierSet(requires)
    assert Version("3.11") in spec
    assert Version("3.12") in spec
    assert Version("3.13") not in spec
