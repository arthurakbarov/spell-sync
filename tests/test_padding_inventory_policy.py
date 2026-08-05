"""Freeze legacy coverage-padding inventory so it cannot grow silently.

Behavioral and invariant tests are preferred (see `docs/TESTING_STRATEGY.md`).
Existing `*coverage*` suites remain as residual R-PWR: freeze + shrink only — move
coverage into behavioral modules, then delete padding tests; never raise the ceiling
without owner approval.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# Frozen at the post-0.3 hardening pass. Do not grow this set without owner approval.
ALLOWED_COVERAGE_NAMED_FILES = frozenset(
    {
        "tests/test_coverage_gaps.py",
        "tests/test_diagnostics_coverage.py",
        "tests/test_execution_group_coverage.py",
        "tests/test_line_coverage_gaps.py",
        "tests/test_phase4_facade_coverage.py",
        "tests/test_project_setup_coverage.py",
        "tests/test_push_safety_coverage.py",
        "tests/test_recovery_facade_coverage.py",
        "tests/test_security_hardening_coverage.py",
        "tests/test_transparency_coverage.py",
        "tests/test_trusted_internal_fs_coverage.py",
        "tests/tui/test_phase4_coverage.py",
        "tests/tui/test_phase5_coverage.py",
        "tests/tui/test_review_coverage.py",
        "tests/tui/test_screen_coverage.py",
        "tests/tui/test_setup_targets_coverage.py",
        "tests/tui/test_target_settings_coverage.py",
    }
)

# Count only def test_ inside ALLOWED_COVERAGE_NAMED_FILES.
# Shrunk from 372 when removing a duplicate recover-path padding test (R-PWR).
MAX_COVERAGE_NAMED_TEST_DEFS = 371

# Explicitly removed padding / re-export shims — must not return under a new name-free path.
REMOVED_PADDING_FILES = frozenset(
    {
        "tests/test_execution_interrupt.py",
        "tests/tui/test_button_else_branches.py",
    }
)

# Handler-style suites must assert outcomes (not click-and-hope coverage).
VERIFIED_HANDLER_FILES = frozenset(
    {
        "tests/tui/test_setup_screen_handlers.py",
    }
)


def _looks_like_padding(path: Path) -> bool:
    """Legacy padding suites: *_coverage.py or *coverage_gaps*.py — not policy tests."""
    name = path.name
    return name.endswith("_coverage.py") or "coverage_gaps" in name


def _coverage_named_files() -> list[Path]:
    return sorted(
        path for path in TESTS.rglob("*.py") if path.is_file() and _looks_like_padding(path)
    )


def _test_functions(path: Path) -> list[ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _has_verification(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                return True
            if isinstance(func, ast.Attribute) and func.attr == "fail":
                return True
            if isinstance(func, ast.Name) and func.id in {"raises", "warns", "deprecated_call"}:
                return True
            if isinstance(func, ast.Attribute) and func.attr in {"raises", "warns"}:
                return True
    return False


def test_coverage_named_files_are_frozen() -> None:
    found = {path.relative_to(ROOT).as_posix() for path in _coverage_named_files()}
    unexpected = sorted(found - ALLOWED_COVERAGE_NAMED_FILES)
    missing = sorted(ALLOWED_COVERAGE_NAMED_FILES - found)
    assert not unexpected, f"new coverage-padding files are forbidden: {unexpected}"
    assert not missing, f"frozen coverage-padding files disappeared: {missing}"


def test_coverage_named_test_count_does_not_grow() -> None:
    total = 0
    for rel in sorted(ALLOWED_COVERAGE_NAMED_FILES):
        text = (ROOT / rel).read_text(encoding="utf-8")
        total += text.count("def test_")
    assert total <= MAX_COVERAGE_NAMED_TEST_DEFS, (
        f"coverage-named test defs grew to {total} (max {MAX_COVERAGE_NAMED_TEST_DEFS})"
    )


def test_removed_padding_files_stay_gone() -> None:
    survivors = [rel for rel in sorted(REMOVED_PADDING_FILES) if (ROOT / rel).is_file()]
    assert not survivors, f"removed padding files returned: {survivors}"


def test_handler_suites_verify_outcomes() -> None:
    bare: list[str] = []
    for rel in sorted(VERIFIED_HANDLER_FILES):
        path = ROOT / rel
        assert path.is_file(), f"missing handler suite: {rel}"
        for node in _test_functions(path):
            if not _has_verification(node):
                bare.append(f"{rel}::{node.name}")
    assert not bare, f"handler tests must assert an outcome: {bare}"
