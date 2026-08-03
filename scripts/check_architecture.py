#!/usr/bin/env python3
"""Architecture boundary validator for spell-sync."""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import pkgutil
import sys
import tomllib
from dataclasses import dataclass, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_ID = "ARCH"
PROJECT_MAP_PATH = ROOT / "docs" / "PROJECT_MAP.md"
PROJECT_MAP_START = "[project-map:start]"
PROJECT_MAP_END = "[project-map:end]"
TEST_GROUPS_PATH = ROOT / "ci" / "test-groups.toml"

REQUIRED_PROJECT_MAP_HEADINGS = (
    "# Project map",
    "## Entry points",
    "## Layers and allowed dependencies",
    "## Application requests",
    "## Services",
    "## Core mutation modules",
    "## Diagnostics and history",
    "## TUI flows",
    "## Target discovery",
    "## Package resources",
    "## Test suites by responsibility",
    "## Common change recipes",
)

EXPECTED_APPLICATION_EXPORTS = frozenset(
    {
        "DashboardIssue",
        "DashboardSeverity",
        "DashboardState",
        "DoctorCheckView",
        "DoctorSnapshot",
        "EventId",
        "EventLevel",
        "EventSink",
        "OperationKind",
        "OperationOutcome",
        "OperationPhase",
        "OperationReport",
        "PresentedEvent",
        "PullExecution",
        "PullPreview",
        "PullSourcePreview",
        "PushExecution",
        "PushPreview",
        "RecoveryExecution",
        "RecoveryItemPreview",
        "RecoveryOutcome",
        "RecoveryPreview",
        "RecoveryStatus",
        "RuntimeResolver",
        "SpellSyncService",
        "StatusDetailSnapshot",
        "StatusSnapshot",
        "TargetPreview",
        "TargetStatusRow",
        "TargetUpdateReport",
        "TechnicalEvent",
    }
)

APPLICATION_IMPORT_BANS = (
    "argparse",
    "cli_options",
    "cli_request_adapter",
    "textual",
)

TUI_IMPORT_BANS = (
    "push_transaction",
    "push_render",
    "execute_prepared_push",
    "recover_from_journal",
    "discard_journal",
    "push_journal",
    "PushJournalSession",
)

TUI_SOURCE_BANS = (
    "atomic_write",
    "subprocess",
    "os.system",
)

FACADE_IMPORT_BANS = (
    "push_journal",
    "push_transaction",
    "recover_from_journal",
    "execute_prepared_push",
    "atomic_write",
)

# CLI entry surface may import application; core / project_setup must not.
DEP_ALLOWED_APPLICATION_IMPORTERS = frozenset(
    {
        "cli.py",
        "cli_request_adapter.py",
        "command_helpers.py",
        "commands.py",
        "doctor.py",
        "plan_cmd.py",
        "recover_cmd.py",
        "removal_review.py",
        "support_report_cmd.py",
    }
)
# Documented layering inversion: diagnostics history/types depend on application report DTOs.
DEP_KNOWN_APPLICATION_EXCEPTIONS = frozenset(
    {
        "diagnostics/history_builder.py",
        "diagnostics/history_store.py",
        "diagnostics/technical_event_builder.py",
        "diagnostics/types.py",
    }
)
DEP_EXEMPT_PACKAGES = frozenset({"application", "tui"})
RT_CONTEXTVAR_EXEMPT_PACKAGES = frozenset({"bundled"})

REQUEST_CLASS_NAMES = (
    "ProjectRef",
    "StatusRequest",
    "DoctorRequest",
    "PullRequest",
    "PushRequest",
    "RecoveryRequest",
    "SetupRequest",
    "TargetSettingsRequest",
    "PrepareTargetSettingsUpdateRequest",
    "SupportReportRequest",
)


@dataclass(frozen=True, slots=True)
class ArchitectureViolation:
    check_id: str
    path: Path | None
    detail: str
    remediation: str


def _format_violation(violation: ArchitectureViolation) -> str:
    location = str(violation.path.relative_to(ROOT)) if violation.path else "<repo>"
    return f"[{violation.check_id}] {location}: {violation.detail} — {violation.remediation}"


def _python_modules(package_path: Path, package_name: str) -> list[tuple[str, Path]]:
    modules: list[tuple[str, Path]] = []
    for module_info in pkgutil.walk_packages([str(package_path)], prefix=f"{package_name}."):
        module = importlib.import_module(module_info.name)
        source_path = getattr(module, "__file__", "") or ""
        if source_path.endswith(".py"):
            modules.append((module_info.name, Path(source_path)))
    return modules


def _module_import_hits(source_path: Path, banned: tuple[str, ...]) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for token in banned:
                    if token in alias.name:
                        hits.append(f"import {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            for token in banned:
                if token in node.module:
                    hits.append(f"from {node.module}")
    return hits


def _module_package(source_path: Path) -> str:
    """Dotted package that anchors relative imports in this file."""
    rel = source_path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] != "__init__":
        parts.pop()
    return ".".join(parts)


def _is_type_checking_test(test: ast.AST) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _type_checking_guarded_nodes(tree: ast.AST) -> set[ast.AST]:
    guarded: set[ast.AST] = set()
    for parent in ast.walk(tree):
        if isinstance(parent, ast.If) and _is_type_checking_test(parent.test):
            for node in ast.walk(parent):
                guarded.add(node)
    return guarded


def _resolve_import_from(package: str, node: ast.ImportFrom) -> str:
    """Resolve ImportFrom to an absolute dotted module name."""
    if node.level == 0:
        return node.module or ""
    anchor = package.split(".") if package else []
    if node.level > 1:
        anchor = anchor[: len(anchor) - (node.level - 1)]
    if node.module:
        return ".".join([*anchor, node.module])
    return ".".join(anchor)


def _resolved_application_import_hits(source_path: Path) -> list[str]:
    """Return rendered imports that resolve to spell_sync.application (runtime only)."""
    package = _module_package(source_path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    guarded = _type_checking_guarded_nodes(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if node in guarded:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute = alias.name
                if absolute == "spell_sync.application" or absolute.startswith(
                    "spell_sync.application."
                ):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            absolute = _resolve_import_from(package, node)
            if absolute == "spell_sync.application" or absolute.startswith(
                "spell_sync.application."
            ):
                dots = "." * node.level
                module = node.module or ""
                hits.append(f"from {dots}{module} resolves to {absolute}")
    return hits


def _uses_contextvar(source_path: Path) -> bool:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "ContextVar":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "ContextVar":
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "contextvars" or alias.name.startswith("contextvars."):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module == "contextvars":
            return True
    return False


def _source_token_hits(source_path: Path, banned: tuple[str, ...]) -> list[str]:
    source = source_path.read_text(encoding="utf-8")
    return [token for token in banned if token in source]


def _check_application_imports() -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    app_root = ROOT / "spell_sync" / "application"
    for module_name, source_path in _python_modules(app_root, "spell_sync.application"):
        for hit in _module_import_hits(source_path, APPLICATION_IMPORT_BANS):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-APP-001",
                    source_path,
                    hit,
                    "keep CLI/TUI/parser imports out of application layer",
                )
            )
    return violations


def _check_tui_boundaries() -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    tui_root = ROOT / "spell_sync" / "tui"
    for module_name, source_path in _python_modules(tui_root, "spell_sync.tui"):
        for hit in _module_import_hits(source_path, TUI_IMPORT_BANS):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-TUI-001",
                    source_path,
                    hit,
                    "route mutations through SpellSyncService, not core writers",
                )
            )
        for hit in _source_token_hits(source_path, TUI_SOURCE_BANS):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-TUI-002",
                    source_path,
                    f"references {hit}",
                    "TUI must not shell out or call low-level writers directly",
                )
            )
    return violations


def _check_cli_options_isolation() -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    for package_name, package_path in (
        ("spell_sync.application", ROOT / "spell_sync" / "application"),
        ("spell_sync.tui", ROOT / "spell_sync" / "tui"),
        ("spell_sync.project_setup", ROOT / "spell_sync" / "project_setup"),
        ("spell_sync.diagnostics", ROOT / "spell_sync" / "diagnostics"),
    ):
        if not package_path.is_dir():
            continue
        for module_name, source_path in _python_modules(package_path, package_name):
            for hit in _module_import_hits(source_path, ("cli_options",)):
                violations.append(
                    ArchitectureViolation(
                        f"{CHECK_ID}-CLI-001",
                        source_path,
                        hit,
                        "map CliOptions only in cli_request_adapter",
                    )
                )
    return violations


def _check_contextvars() -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    spell_sync = ROOT / "spell_sync"
    for path in sorted(spell_sync.rglob("*.py")):
        rel = path.relative_to(spell_sync)
        if rel.parts and rel.parts[0] in RT_CONTEXTVAR_EXEMPT_PACKAGES:
            continue
        if _uses_contextvar(path):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-RT-001",
                    path,
                    "uses ContextVar",
                    "use explicit RuntimeResolver and scoped parameters",
                )
            )
    return violations


def _check_facade_imports() -> list[ArchitectureViolation]:
    facade = ROOT / "spell_sync" / "application" / "service.py"
    violations: list[ArchitectureViolation] = []
    for hit in _module_import_hits(facade, FACADE_IMPORT_BANS):
        violations.append(
            ArchitectureViolation(
                f"{CHECK_ID}-FAC-001",
                facade,
                hit,
                "facade must delegate to focused services",
            )
        )
    return violations


def _check_request_dataclasses() -> list[ArchitectureViolation]:
    from spell_sync.application import requests as requests_mod

    violations: list[ArchitectureViolation] = []
    for name in REQUEST_CLASS_NAMES:
        cls = getattr(requests_mod, name, None)
        if cls is None:
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-REQ-001",
                    Path(requests_mod.__file__ or ""),
                    f"missing request class {name}",
                    "keep typed request DTOs in application/requests.py",
                )
            )
            continue
        if not is_dataclass(cls):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-REQ-002",
                    Path(requests_mod.__file__ or ""),
                    f"{name} is not a dataclass",
                    "requests must be dataclasses",
                )
            )
            continue
        if not getattr(cls, "__dataclass_params__").frozen:
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-REQ-003",
                    Path(requests_mod.__file__ or ""),
                    f"{name} is not frozen",
                    "requests must be immutable",
                )
            )
    return violations


def _check_event_ids() -> list[ArchitectureViolation]:
    from spell_sync.diagnostics.technical_event_model import EventId

    violations: list[ArchitectureViolation] = []
    values = [member.value for member in EventId]
    if len(values) != len(set(values)):
        violations.append(
            ArchitectureViolation(
                f"{CHECK_ID}-EVT-001",
                Path(inspect.getfile(EventId)),
                "duplicate EventId values",
                "event identifiers must be unique",
            )
        )
    return violations


def _check_application_exports() -> list[ArchitectureViolation]:
    from spell_sync.application import __all__ as application_all

    violations: list[ArchitectureViolation] = []
    actual = frozenset(application_all)
    if actual != EXPECTED_APPLICATION_EXPORTS:
        missing = sorted(EXPECTED_APPLICATION_EXPORTS - actual)
        extra = sorted(actual - EXPECTED_APPLICATION_EXPORTS)
        detail_parts: list[str] = []
        if missing:
            detail_parts.append(f"missing exports {missing}")
        if extra:
            detail_parts.append(f"unexpected exports {extra}")
        violations.append(
            ArchitectureViolation(
                f"{CHECK_ID}-PUB-001",
                ROOT / "spell_sync" / "application" / "__init__.py",
                "; ".join(detail_parts) or "public exports changed",
                "update EXPECTED_APPLICATION_EXPORTS deliberately when changing __all__",
            )
        )
    return violations


def _check_core_does_not_import_application() -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    spell_sync = ROOT / "spell_sync"
    allowed = DEP_ALLOWED_APPLICATION_IMPORTERS | DEP_KNOWN_APPLICATION_EXCEPTIONS
    for path in sorted(spell_sync.rglob("*.py")):
        rel = path.relative_to(spell_sync)
        if rel.parts and rel.parts[0] in DEP_EXEMPT_PACKAGES:
            continue
        if rel.as_posix() in allowed:
            continue
        for hit in _resolved_application_import_hits(path):
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-DEP-001",
                    path,
                    hit,
                    "core must not import application layer",
                )
            )
    return violations


def _generated_project_map_section() -> str:
    data = tomllib.loads(TEST_GROUPS_PATH.read_text(encoding="utf-8"))
    lines = [
        "_Generated by `scripts/check_architecture.py`; do not edit manually._",
        "",
        "| Group | Responsibility |",
        "|-------|----------------|",
    ]
    for group in data.get("groups", []):
        group_id = group.get("id", "")
        description = group.get("description", "")
        lines.append(f"| `{group_id}` | {description} |")
    lines.append("")
    lines.append("Run grouped CI via `scripts/ci_runner.py` or `scripts/ci.sh`.")
    lines.append("")
    return "\n".join(lines)


def _replace_generated_section(content: str, generated: str) -> str:
    if PROJECT_MAP_START not in content or PROJECT_MAP_END not in content:
        raise ValueError("project map markers missing")
    before, rest = content.split(PROJECT_MAP_START, 1)
    _, after = rest.split(PROJECT_MAP_END, 1)
    return f"{before}{PROJECT_MAP_START}\n{generated}{PROJECT_MAP_END}{after}"


def _check_project_map(*, write: bool) -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    if not PROJECT_MAP_PATH.is_file():
        return [
            ArchitectureViolation(
                f"{CHECK_ID}-MAP-001",
                PROJECT_MAP_PATH,
                "missing project map",
                "create docs/PROJECT_MAP.md",
            )
        ]

    content = PROJECT_MAP_PATH.read_text(encoding="utf-8")
    for heading in REQUIRED_PROJECT_MAP_HEADINGS:
        if heading not in content:
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-MAP-002",
                    PROJECT_MAP_PATH,
                    f"missing heading {heading!r}",
                    "add required project map section",
                )
            )

    if PROJECT_MAP_START not in content or PROJECT_MAP_END not in content:
        violations.append(
            ArchitectureViolation(
                f"{CHECK_ID}-MAP-003",
                PROJECT_MAP_PATH,
                "missing generated section markers",
                f"wrap generated content with {PROJECT_MAP_START} … {PROJECT_MAP_END}",
            )
        )
        return violations

    expected = _generated_project_map_section()
    before, rest = content.split(PROJECT_MAP_START, 1)
    current, after = rest.split(PROJECT_MAP_END, 1)
    current_block = f"{PROJECT_MAP_START}{current}{PROJECT_MAP_END}"
    expected_block = f"{PROJECT_MAP_START}\n{expected}{PROJECT_MAP_END}"
    if current_block != expected_block:
        if write:
            PROJECT_MAP_PATH.write_text(
                _replace_generated_section(content, expected),
                encoding="utf-8",
            )
        else:
            violations.append(
                ArchitectureViolation(
                    f"{CHECK_ID}-MAP-004",
                    PROJECT_MAP_PATH,
                    "generated project map section is stale",
                    "run scripts/check_architecture.py --write",
                )
            )
    return violations


def collect_violations(*, write_project_map: bool) -> list[ArchitectureViolation]:
    violations: list[ArchitectureViolation] = []
    violations.extend(_check_application_imports())
    violations.extend(_check_tui_boundaries())
    violations.extend(_check_cli_options_isolation())
    violations.extend(_check_contextvars())
    violations.extend(_check_facade_imports())
    violations.extend(_check_request_dataclasses())
    violations.extend(_check_event_ids())
    violations.extend(_check_application_exports())
    violations.extend(_check_core_does_not_import_application())
    violations.extend(_check_project_map(write=write_project_map))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate spell-sync architecture boundaries.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate architecture boundaries (default).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the project map generated section when stale.",
    )
    args = parser.parse_args(argv)
    if not args.check and not args.write:
        args.check = True

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    violations = collect_violations(write_project_map=args.write)
    if violations:
        sys.stderr.write("\n".join(_format_violation(item) for item in violations) + "\n")
        return 1

    print("ARCHITECTURE_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
