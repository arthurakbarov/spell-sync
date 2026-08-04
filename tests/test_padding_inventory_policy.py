"""Freeze legacy coverage-padding inventory so it cannot grow silently.

Behavioral and invariant tests are preferred (see `docs/TESTING_STRATEGY.md`).
Existing `*coverage*` suites remain as residual R-PWR: freeze + shrink only — move
coverage into behavioral modules, then delete padding tests; never raise the ceiling
without owner approval.
"""

from __future__ import annotations

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

# Ceiling includes this policy module's own tests once collected elsewhere —
# count only def test_ inside ALLOWED_COVERAGE_NAMED_FILES.
MAX_COVERAGE_NAMED_TEST_DEFS = 373


def _coverage_named_files() -> list[Path]:
    return sorted(path for path in TESTS.rglob("*coverage*.py") if path.is_file())


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
