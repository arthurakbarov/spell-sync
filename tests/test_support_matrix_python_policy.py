"""Negative and positive checks for support-matrix Python policy helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_support_matrix import (  # noqa: E402
    check_blocking_job_forbids_source_only,
    check_pyproject_python_alignment,
)

_BLOCKING = ["3.14"]
_GOOD_CLASSIFIERS = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.14",
]


def test_rejects_missing_blocking_classifier() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.14,<3.15",
        contract_requirement=">=3.14,<3.15",
        blocking=_BLOCKING,
        classifiers=[
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3 :: Only",
        ],
    )
    assert any("missing blocking Python 3.14" in item for item in errors)


def test_rejects_contract_requires_python_mismatch() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.14",
        contract_requirement=">=3.14,<3.15",
        blocking=_BLOCKING,
        classifiers=_GOOD_CLASSIFIERS,
    )
    assert any("must match environment-contract" in item for item in errors)


def test_rejects_classifier_outside_blocking() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.14,<3.15",
        contract_requirement=">=3.14,<3.15",
        blocking=_BLOCKING,
        classifiers=[*_GOOD_CLASSIFIERS, "Programming Language :: Python :: 3.15"],
    )
    assert any("outside contract compatibility lists" in item for item in errors)


def test_rejects_source_only_on_blocking_job() -> None:
    block = """
    name: compatibility
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/run_compatibility_checks.py --platform linux --python-version 3.14 --source-only
    """
    errors = check_blocking_job_forbids_source_only(block, job_name="compatibility-linux-py314")
    assert any("must not use --source-only" in item for item in errors)


def test_accepts_aligned_blocking_metadata() -> None:
    errors = check_pyproject_python_alignment(
        requires_python=">=3.14,<3.15",
        contract_requirement=">=3.14,<3.15",
        blocking=_BLOCKING,
        classifiers=_GOOD_CLASSIFIERS,
    )
    assert errors == []


def test_public_requires_python_excludes_313_for_wheel_metadata() -> None:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    requires = SpecifierSet(">=3.14,<3.15")
    assert Version("3.14") in requires
    assert Version("3.13") not in requires
