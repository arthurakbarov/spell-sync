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


def load_test_groups(manifest_path: Path | None = None) -> tuple[TestGroup, ...]:
    path = manifest_path or MANIFEST_PATH
    if not path.is_file():
        raise FileNotFoundError(f"test group manifest missing: {path}")
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
    if not groups:
        raise ValueError(f"test group manifest has no groups: {path}")
    return tuple(groups)


def all_test_files(root: Path | None = None) -> tuple[Path, ...]:
    base = root or ROOT
    tests_root = base.joinpath("tests")
    found = {path for path in tests_root.rglob("test_*.py") if path.is_file()}
    found.update(path for path in tests_root.rglob("*_test.py") if path.is_file())
    return tuple(sorted(found))


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
    problems: list[str] = []
    for path in all_test_files(base):
        rel = path.relative_to(base).as_posix()
        group_id = assign_group(rel, groups)
        if group_id is None:
            problems.append(f"unassigned:{rel}")
            continue
        assigned[rel] = group_id
    return not problems, problems


def validate_group_order(
    groups: tuple[TestGroup, ...] | None = None,
) -> tuple[bool, list[str]]:
    groups = groups or load_test_groups()
    manifest_ids = tuple(group.group_id for group in groups)
    if manifest_ids == GROUP_ORDER:
        return True, []
    return False, [
        f"GROUP_ORDER={','.join(GROUP_ORDER)}",
        f"manifest={','.join(manifest_ids)}",
    ]


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
        raise ValueError(f"test group has no files: {group_id}")
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
