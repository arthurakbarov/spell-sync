"""Stable pytest group manifest for timing and CI selection."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ci" / "test-groups.toml"

GROUP_ORDER = (
    "tests:tui",
    "tests:dev-tooling",
    "tests:environment",
    "tests:packaging",
    "tests:integration",
    "tests:rest",
)


@dataclass(frozen=True, slots=True)
class TestGroup:
    group_id: str
    execution_id: str
    patterns: tuple[str, ...]
    description: str = ""
    fallback: bool = False


def _default_groups() -> tuple[TestGroup, ...]:
    return (
        TestGroup(
            "tests:tui",
            "tests:tui",
            ("tests/tui/**", "tests/test_gui_smoke.py", "tests/test_tui_*.py"),
            "TUI screens, navigation, wizard, and smoke tests",
        ),
        TestGroup(
            "tests:dev-tooling",
            "tests:dev-tooling",
            (
                "tests/test_execution_*.py",
                "tests/test_ci_*.py",
                "tests/test_test_impact*.py",
                "tests/test_test_selection*.py",
                "tests/test_test_run_ledger*.py",
                "tests/test_run_focused_tests.py",
                "tests/test_run_pre_final_checks.py",
            ),
            "CI timing, admission, evidence, test selection, and agent tooling",
        ),
        TestGroup(
            "tests:environment",
            "tests:environment",
            (
                "tests/test_environment*.py",
                "tests/test_compatibility*.py",
                "tests/test_project_environment*.py",
                "tests/test_snapshot*.py",
                "tests/test_support_matrix*.py",
            ),
            "Environment contract, compatibility, and snapshot policy",
        ),
        TestGroup(
            "tests:packaging",
            "tests:packaging",
            (
                "tests/test_installed_workflow.py",
                "tests/test_wheel*.py",
                "tests/test_package*.py",
            ),
            "Wheel install, packaging, and installed smoke",
        ),
        TestGroup(
            "tests:integration",
            "tests:integration",
            (
                "tests/test_*integration*.py",
                "tests/test_*workflow*.py",
            ),
            "Slow multi-step and subprocess integration flows",
        ),
        TestGroup(
            "tests:rest",
            "tests:rest",
            ("tests/test_*.py",),
            "Unclaimed remainder tests (fallback group)",
            fallback=True,
        ),
    )


def load_test_groups(manifest_path: Path | None = None) -> tuple[TestGroup, ...]:
    path = manifest_path or MANIFEST_PATH
    if not path.is_file():
        return _default_groups()
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    groups: list[TestGroup] = []
    for item in payload.get("groups", []):
        if not isinstance(item, dict):
            continue
        group_id = str(item.get("id", ""))
        execution_id = str(item.get("executionId", group_id))
        patterns = tuple(str(pattern) for pattern in item.get("patterns", []))
        if group_id and patterns:
            groups.append(
                TestGroup(
                    group_id=group_id,
                    execution_id=execution_id,
                    patterns=patterns,
                    description=str(item.get("description", "")),
                    fallback=bool(item.get("fallback", False)),
                )
            )
    return tuple(groups) if groups else _default_groups()


def all_test_files(root: Path | None = None) -> tuple[Path, ...]:
    base = root or ROOT
    return tuple(sorted(base.joinpath("tests").rglob("test_*.py")))


def _matches(pattern: str, rel_path: str) -> bool:
    if fnmatch(rel_path, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel_path.startswith(prefix)
    return False


def _fallback_group_id(groups: tuple[TestGroup, ...]) -> str | None:
    for group in groups:
        if group.fallback:
            return group.group_id
    return None


def assign_group(rel_path: str, groups: tuple[TestGroup, ...]) -> str | None:
    for group in groups:
        if group.fallback:
            continue
        if any(_matches(pattern, rel_path) for pattern in group.patterns):
            return group.group_id
    for group in groups:
        if group.fallback and any(_matches(pattern, rel_path) for pattern in group.patterns):
            return group.group_id
    return None


def group_files(
    group_id: str,
    *,
    root: Path | None = None,
    groups: tuple[TestGroup, ...] | None = None,
) -> tuple[str, ...]:
    groups = groups or load_test_groups()
    selected = next((item for item in groups if item.group_id == group_id), None)
    if selected is None:
        return ()
    files: list[str] = []
    for path in all_test_files(root):
        rel = path.relative_to(root or ROOT).as_posix()
        if assign_group(rel, groups) == group_id:
            files.append(rel)
    return tuple(sorted(files))


def validate_union(
    root: Path | None = None,
    groups: tuple[TestGroup, ...] | None = None,
) -> tuple[bool, list[str]]:
    groups = groups or load_test_groups()
    base = root or ROOT
    assigned: dict[str, str] = {}
    duplicates: list[str] = []
    for path in all_test_files(base):
        rel = path.relative_to(base).as_posix()
        group_id = assign_group(rel, groups)
        if group_id is None:
            duplicates.append(f"unassigned:{rel}")
            continue
        if rel in assigned:
            duplicates.append(f"duplicate:{rel}")
        assigned[rel] = group_id
    missing = [
        path.relative_to(base).as_posix()
        for path in all_test_files(base)
        if path.relative_to(base).as_posix() not in assigned
    ]
    ok = not missing and not duplicates
    return ok, missing + duplicates


def is_pytest_group(step_id: str) -> bool:
    return step_id in GROUP_ORDER


def pytest_command_for_group(
    group_id: str,
    py: str,
    *,
    root: Path | None = None,
    cov_append: bool = False,
    with_coverage: bool = False,
) -> list[str]:
    files = group_files(group_id, root=root)
    if not files:
        return [py, "-m", "pytest", "-q", "--collect-only"]
    command = [py, "-m", "pytest", *files, "-q", "--durations=10"]
    if with_coverage:
        command.extend(
            [
                "--cov=spell_sync",
                "--cov-branch",
                "--cov-report=term-missing:skip-covered",
                "--cov-fail-under=0",
            ]
        )
        if cov_append:
            command.append("--cov-append")
        groups = load_test_groups()
        fallback_id = _fallback_group_id(groups)
        if group_id == fallback_id or (fallback_id is None and group_id == GROUP_ORDER[-1]):
            command.append("--cov-report=json")
    return command
