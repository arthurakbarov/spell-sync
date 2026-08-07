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

# Frozen at the Version 1 hardening pass. Do not grow this set without owner approval.
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

# Bare (no assert/fail/raises) tests inside ALLOWED_COVERAGE_NAMED_FILES — freeze + shrink.
# Strengthened tests must leave this set; new bare tests in frozen files are forbidden.
ALLOWED_BARE_COVERAGE_TESTS = frozenset(
    {
        "tests/test_diagnostics_coverage.py::test_compaction_write_failure",
        "tests/test_diagnostics_coverage.py::test_service_log_setup_warning",
        "tests/test_diagnostics_coverage.py::test_compaction_read_failure",
        "tests/test_diagnostics_coverage.py::test_compaction_temp_unlink_failure",
        "tests/test_diagnostics_coverage.py::test_lock_close_failure",
        "tests/test_diagnostics_coverage.py::test_compaction_cleanup_unlink_failure",
        "tests/test_line_coverage_gaps.py::test_dashboard_corrupt_journal_banner",
        "tests/test_line_coverage_gaps.py::test_operation_cleanup_and_controller_cleanup",
        "tests/test_security_hardening_coverage.py::test_reject_unsafe_nonexistent",
        "tests/test_security_hardening_coverage.py::test_windows_private_helpers",
        "tests/test_security_hardening_coverage.py::test_windows_branches_via_platform_patch",
        "tests/test_security_hardening_coverage.py::test_fsync_fd_enosys_ignored",
        "tests/test_security_hardening_coverage.py::test_flush_windows_nested_oserror",
        "tests/test_security_hardening_coverage.py::test_discard_txn_snapshots_swallows_errors",
        "tests/test_transparency_coverage.py::test_doctor_export_file_exists",
        "tests/test_transparency_coverage.py::test_target_settings_open_details_without_focus",
        "tests/test_transparency_coverage.py::test_doctor_export_generic_failure",
        "tests/test_transparency_coverage.py::test_review_save_report_already_saved_message",
        "tests/test_trusted_internal_fs_coverage.py::test_fchmod_private_fd_on_unix",
        "tests/test_trusted_internal_fs_coverage.py::test_fchmod_win32_noop",
        "tests/test_trusted_internal_fs_coverage.py::test_flush_file_buffers_failure",
        "tests/test_trusted_internal_fs_coverage.py::test_ensure_child_directory_eexist_oserror",
        "tests/test_trusted_internal_fs_coverage.py::test_fchmod_private_win32",
        "tests/test_trusted_internal_fs_coverage.py::test_reject_unsafe_component_file_and_dir",
        "tests/tui/test_phase4_coverage.py::test_operation_event_and_cancel_policy",
        "tests/tui/test_phase4_coverage.py::test_operation_blocked_second_mutation",
        "tests/tui/test_phase4_coverage.py::test_operation_apply_event_branches",
        "tests/tui/test_phase4_coverage.py::test_report_details_rebuild_and_quit",
        "tests/tui/test_phase4_coverage.py::test_push_confirm_view_removals",
        "tests/tui/test_phase4_coverage.py::test_operation_worker_poll_error",
        "tests/tui/test_phase4_coverage.py::test_operation_null_result_and_bindings",
        "tests/tui/test_phase4_coverage.py::test_operation_callback_paths",
        "tests/tui/test_phase4_coverage.py::test_pull_screen_mount_exception",
        "tests/tui/test_phase4_coverage.py::test_push_confirm_typed_guard_and_non_typed_input",
        "tests/tui/test_phase4_coverage.py::test_report_quit_and_details_recovery",
        "tests/tui/test_phase4_coverage.py::test_operation_unmounted_and_finished_guards",
        "tests/tui/test_phase4_coverage.py::test_operation_worker_success_callback",
        "tests/tui/test_phase5_coverage.py::test_recovery_mount_inspection_failure",
        "tests/tui/test_phase5_coverage.py::test_recovery_view_details_and_back",
        "tests/tui/test_phase5_coverage.py::test_recovery_confirm_cleanup_and_cancel",
        "tests/tui/test_phase5_coverage.py::test_recovery_confirm_cancel_and_discard_cancel",
        "tests/tui/test_review_coverage.py::test_start_screen_back_paths",
        "tests/tui/test_review_coverage.py::test_session_report_back_on_shallow_stack",
        "tests/tui/test_review_coverage.py::test_session_report_back_dashboard_refresh",
        "tests/tui/test_setup_targets_coverage.py::test_focus_navigation_without_rows",
        "tests/tui/test_setup_targets_coverage.py::test_checkbox_changed_and_disabled_toggle",
        "tests/tui/test_setup_targets_coverage.py::test_button_handlers",
        "tests/tui/test_setup_targets_coverage.py::test_focus_from_button",
        "tests/tui/test_setup_targets_coverage.py::test_focused_property_branches",
        "tests/tui/test_setup_targets_coverage.py::test_key_space_on_selectable_row",
        "tests/tui/test_target_settings_coverage.py::test_operation_targets_flow",
        "tests/tui/test_target_settings_coverage.py::test_row_widget_meta_lines",
        "tests/tui/test_target_settings_coverage.py::test_row_widget_checkbox_paths",
    }
)
MAX_BARE_COVERAGE_TESTS = 53


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


def _bare_coverage_tests() -> set[str]:
    found: set[str] = set()
    for rel in sorted(ALLOWED_COVERAGE_NAMED_FILES):
        path = ROOT / rel
        for node in _test_functions(path):
            if not _has_verification(node):
                found.add(f"{rel}::{node.name}")
    return found


def test_bare_coverage_tests_are_frozen() -> None:
    found = _bare_coverage_tests()
    unexpected = sorted(found - ALLOWED_BARE_COVERAGE_TESTS)
    # Allowlist may retain names after a test gains asserts (shrink); those are ignored.
    assert not unexpected, f"new bare coverage-padding tests are forbidden: {unexpected}"
    assert len(found) <= MAX_BARE_COVERAGE_TESTS, (
        f"bare coverage-padding tests grew to {len(found)} (max {MAX_BARE_COVERAGE_TESTS})"
    )
