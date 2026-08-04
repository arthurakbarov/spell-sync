#!/usr/bin/env python3
"""Tests for CI impact classification and input digest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_impact.constants import (  # noqa: E402
    FULL_CI_CHANGE_CLASSES,
    NON_CI_CHANGE_CLASSES,
    ChangeClass,
)
from scripts.ci_impact.registry import (  # noqa: E402
    classify_path,
    load_registry,
    requires_full_ci,
    validate_registry,
)
from scripts.ci_input_state import compute_ci_input_state  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    return load_registry(ROOT / "ci" / "ci-impact.toml")


def test_non_ci_classes_exclude_validators() -> None:
    assert ChangeClass.VALIDATOR in FULL_CI_CHANGE_CLASSES
    assert ChangeClass.VALIDATOR not in NON_CI_CHANGE_CLASSES
    assert ChangeClass.DOCUMENTATION in NON_CI_CHANGE_CLASSES


def test_registry_covers_tracked_paths(registry) -> None:
    assert validate_registry(ROOT, registry) == []


def test_product_and_documentation_classification(registry) -> None:
    assert classify_path("spell_sync/cli.py", registry) is ChangeClass.PRODUCT
    assert classify_path("docs/ARCHITECTURE.md", registry) is ChangeClass.DOCUMENTATION
    assert (
        classify_path(".cursor/rules/test-efficiency.mdc", registry) is ChangeClass.AGENT_WORKFLOW
    )


def test_full_ci_classes(registry) -> None:
    assert requires_full_ci(classify_path("tests/test_core.py", registry))
    assert requires_full_ci(classify_path("pyproject.toml", registry))
    assert requires_full_ci(classify_path("scripts/ci_runner.py", registry))
    assert requires_full_ci(classify_path("scripts/check_architecture.py", registry))
    assert not requires_full_ci(classify_path("docs/TESTING_STRATEGY.md", registry))


def test_ci_input_digest_ignores_documentation_changes(registry, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git(repo)
    (repo / "ci").mkdir()
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(), encoding="utf-8"
    )
    (repo / "spell_sync").mkdir()
    (repo / "spell_sync" / "sample.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("docs\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "init")
    before = compute_ci_input_state(repo, load_registry(repo / "ci" / "ci-impact.toml")).digest
    (repo / "docs" / "note.md").write_text("docs updated\n", encoding="utf-8")
    after = compute_ci_input_state(repo, load_registry(repo / "ci" / "ci-impact.toml")).digest
    assert before == after


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)


def _git_add_all(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)


def _git_commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True
    )
