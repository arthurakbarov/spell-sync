#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Documentation contract tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRACKER_TEMPLATE = """# Tracker

## Current phase

{body}

[architecture-status:start]
{status_block}
[architecture-status:end]
"""

MINIMAL_REPO = {
    "pyproject.toml": (
        '[project]\nname = "spell-sync"\nversion = "9.9.9"\nrequires-python = ">=3.11"\n'
    ),
    "AGENTS.md": ("# Agents\n\n```text agent-config-cli-commands\n`version`\n```\n"),
    "spell_sync/cli.py": "COMMANDS = {'version': None}\n",
    "docs/AGENT_DEVELOPMENT.md": "# Agent development\n",
}


def _load_docs_contract():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import check_docs_contract

    return check_docs_contract


def _init_synthetic_repo(
    root: Path,
    extra: dict[str, str] | None = None,
    *,
    base: dict[str, str] | None = None,
) -> None:
    files = dict(base if base is not None else MINIMAL_REPO)
    if extra:
        files.update(extra)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "add", "-A"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )


class TestDocsContract(unittest.TestCase):
    def test_docs_contract_script_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/check_docs_contract.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"[DOCS-CONTRACT-001] docs contract failed:\n{proc.stdout}\n{proc.stderr}",
        )

    def test_validator_has_no_hardcoded_phase_gate(self) -> None:
        text = (ROOT / "scripts" / "check_docs_contract.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "Phase 3 must not be started",
            text,
            msg="[DOCS-CONTRACT-002] validator must not hardcode phase gate text",
        )
        self.assertNotIn(
            "Phase 3 remains future work",
            text,
            msg="[DOCS-CONTRACT-003] validator must not hardcode Phase 3 completion ban",
        )
        self.assertNotIn(
            "version must be 0.2.1",
            text,
            msg="[DOCS-CONTRACT-004] validator must not hardcode release version",
        )

    def test_current_tracker_passes(self) -> None:
        mod = _load_docs_contract()
        violations = mod.check_repository(ROOT)
        phase_hits = [v for v in violations if v.check_id.startswith("PHASE-")]
        self.assertEqual(phase_hits, [], msg="[DOCS-CONTRACT-005] current tracker phase checks")

    def test_phase_three_in_progress_passes(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-3",
                    "phase-3: in-progress",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Phase 3 explicit runtime is active.",
                        status_block=status,
                    ),
                },
            )
            violations = mod.check_repository(root)
            self.assertEqual(
                [v.check_id for v in violations if v.check_id.startswith("PHASE-")],
                [],
                msg="[DOCS-CONTRACT-006] Phase 3 in-progress must pass",
            )

    def test_phase_three_complete_passes(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-4",
                    "phase-3: complete",
                    "phase-4: planned",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Phase 3 complete; planning Phase 4.",
                        status_block=status,
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id.startswith("PHASE-")]
            self.assertEqual(violations, [], msg="[DOCS-CONTRACT-007] Phase 3 complete must pass")

    def test_future_phase_eight_passes(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-8",
                    "phase-8: planned",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Future phase planning.",
                        status_block=status,
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id.startswith("PHASE-")]
            self.assertEqual(violations, [], msg="[DOCS-CONTRACT-008] future phase must pass")

    def test_duplicate_current_section_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = (
                "## Current phase\n\nActive.\n\n## Current phase\n\nDuplicate.\n\n"
                "[architecture-status:start]\ncurrent: phase-1\nphase-1: complete\n"
                "[architecture-status:end]\n"
            )
            _init_synthetic_repo(root, {"docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": tracker})
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "PHASE-002" for v in violations),
                msg="[DOCS-CONTRACT-009] duplicate current section must fail",
            )

    def test_empty_current_section_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = (
                "## Current phase\n\n\n[architecture-status:start]\n"
                "current: phase-1\nphase-1: complete\n[architecture-status:end]\n"
            )
            _init_synthetic_repo(root, {"docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": tracker})
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "PHASE-003" for v in violations),
                msg="[DOCS-CONTRACT-010] empty current section must fail",
            )

    def test_unknown_status_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = TRACKER_TEMPLATE.format(
                body="Bad status.",
                status_block="current: phase-1\nphase-1: finished",
            )
            _init_synthetic_repo(root, {"docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": tracker})
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "PHASE-008" for v in violations),
                msg="[DOCS-CONTRACT-011] unknown status must fail",
            )

    def test_missing_agent_contract_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = {
                key: value
                for key, value in MINIMAL_REPO.items()
                if key != "docs/AGENT_DEVELOPMENT.md"
            }
            _init_synthetic_repo(root, base=base)
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "AGENT-001" for v in violations),
                msg="[DOCS-CONTRACT-012] missing agent contract must fail",
            )

    def test_cli_command_mismatch_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "AGENTS.md": (
                        "# Agents\n\n```text agent-config-cli-commands\n`status`, `version`\n```\n"
                    ),
                },
            )
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "CLI-001" for v in violations),
                msg="[DOCS-CONTRACT-013] CLI mismatch must fail",
            )

    def test_stale_active_api_fails_with_path_and_line(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {"docs/EXAMPLE.md": "Use OperationSource for routing.\n"},
            )
            violations = mod.check_repository(root)
            api = [v for v in violations if v.check_id == "API-001"]
            self.assertEqual(len(api), 1, msg="[DOCS-CONTRACT-014] stale API must fail")
            self.assertEqual(api[0].path, root / "docs/EXAMPLE.md")
            self.assertEqual(api[0].line_no, 1)

    def test_historical_api_allowed(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "docs/EXAMPLE.md": (
                        "Historical context: removed API\nOperationSource was removed.\n"
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "API-001"]
            self.assertEqual(violations, [], msg="[DOCS-CONTRACT-015] historical API allowed")

    def test_repeated_line_context_window(self) -> None:
        mod = _load_docs_contract()
        lines = [
            "Historical context: removed API",
            "allow_new_project_wizard was removed",
            "Unrelated section",
            "Historical context: removed API",
            "allow_new_project_wizard was removed again",
        ]
        self.assertTrue(mod._line_has_historical_context(lines, 1))
        self.assertTrue(mod._line_has_historical_context(lines, 4))
        self.assertFalse(mod._line_has_historical_context(["allow_new_project_wizard active"], 0))

    def test_future_package_version_does_not_require_validator_change(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "pyproject.toml": (
                        '[project]\nname="x"\nversion="99.0.0"\nrequires-python=">=3.11"\n'
                    ),
                },
            )
            version = mod._project_version(root)
            self.assertEqual(version, "99.0.0", msg="[DOCS-CONTRACT-016] dynamic version read")

    def test_current_points_to_complete_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-2d",
                    "phase-2d: complete",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Invalid current pointer.",
                        status_block=status,
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "PHASE-009"]
            self.assertEqual(len(violations), 1, msg="[DOCS-CONTRACT-017] complete current fails")

    def test_current_points_to_not_started_passes(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-3",
                    "phase-2e: complete",
                    "phase-3: not-started",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Phase 3 is next.",
                        status_block=status,
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id.startswith("PHASE-")]
            self.assertEqual(violations, [], msg="[DOCS-CONTRACT-018] not-started current passes")

    def test_pinned_python_in_agent_docs_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "AGENTS.md": "# Agents\n\n```bash\npython3.11 -m pytest\n```\n",
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "AGENT-004"]
            self.assertEqual(len(violations), 1, msg="[DOCS-CONTRACT-019] pinned python fails")

    def test_development_version_duplication_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "docs/DEVELOPMENT.md": "Version currently 9.9.9 in pyproject.\n",
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "VERSION-002"]
            self.assertEqual(
                len(violations),
                1,
                msg="[DOCS-CONTRACT-020] version duplication fails",
            )

    def test_awaiting_approval_must_be_current_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = "\n".join(
                [
                    "current: phase-3",
                    "phase-3: in-progress",
                    "phase-4: awaiting-approval",
                ]
            )
            _init_synthetic_repo(
                root,
                {
                    "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": TRACKER_TEMPLATE.format(
                        body="Invalid awaiting on non-current.",
                        status_block=status,
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "PHASE-011"]
            self.assertEqual(len(violations), 1, msg="[DOCS-CONTRACT-021] awaiting must be current")

    def test_duplicate_phase_section_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = (
                "## Current phase\n\nPhase 4 active.\n\n"
                "[architecture-status:start]\n"
                "current: phase-4\n"
                "phase-4: awaiting-approval\n"
                "[architecture-status:end]\n\n"
                "## Phase 4 — Focused application services and thin facade\n\n"
                "First.\n\n"
                "## Phase 4 — Focused application services and thin facade\n\n"
                "Duplicate.\n"
            )
            _init_synthetic_repo(root, {"docs/ARCHITECTURE_0_3_IMPLEMENTATION.md": tracker})
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id == "PHASE-013" for v in violations),
                msg="[DOCS-CONTRACT-PHASE-013] duplicate architecture phase section must fail",
            )

    def test_tui_cli_command_count_mismatch_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = (
                "config-check",
                "doctor",
                "init",
                "lint",
                "plan",
                "pull",
                "push",
                "recover",
                "status",
                "support-report",
                "ui",
                "version",
            )
            agents = (
                "# Agents\n\n```text agent-config-cli-commands\n"
                + ", ".join(f"`{name}`" for name in commands)
                + "\n```\n"
            )
            cli = "COMMANDS = {" + ", ".join(f"'{name}': None" for name in commands) + "}\n"
            _init_synthetic_repo(
                root,
                {
                    "AGENTS.md": agents,
                    "spell_sync/cli.py": cli,
                    "docs/TUI_IMPLEMENTATION.md": (
                        "### CLI commands (11)\n\n"
                        "`config-check`, `doctor`, `init`, `lint`, `plan`, `pull`, "
                        "`push`, `recover`, `status`, `ui`, `version`\n"
                    ),
                },
            )
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id in {"CLI-003", "CLI-004"} for v in violations),
                msg="[DOCS-CONTRACT-CLI-LIST] stale TUI CLI list must fail",
            )

    def test_manual_testing_help_omits_support_report_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = (
                "config-check",
                "doctor",
                "init",
                "lint",
                "plan",
                "pull",
                "push",
                "recover",
                "status",
                "support-report",
                "ui",
                "version",
            )
            agents = (
                "# Agents\n\n```text agent-config-cli-commands\n"
                + ", ".join(f"`{name}`" for name in commands)
                + "\n```\n"
            )
            cli = "COMMANDS = {" + ", ".join(f"'{name}': None" for name in commands) + "}\n"
            _init_synthetic_repo(
                root,
                {
                    "AGENTS.md": agents,
                    "spell_sync/cli.py": cli,
                    "docs/MANUAL_TESTING.md": (
                        "Expected:\n\n"
                        "- Help lists commands: `status`, `pull`, `push`, `plan`, "
                        "`config-check`, `lint`, `recover`,\n"
                        "  `init`, `doctor`, `version`, `ui`.\n"
                    ),
                },
            )
            violations = [v for v in mod.check_repository(root) if v.check_id == "CLI-005"]
            self.assertEqual(
                len(violations),
                1,
                msg="[DOCS-CONTRACT-CLI-HELP] MANUAL_TESTING must list support-report",
            )

    def test_test_report_template_stale_title_fails(self) -> None:
        mod = _load_docs_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_synthetic_repo(
                root,
                {
                    "docs/TEST_REPORT_TEMPLATE.md": "# Spell Sync 0.2.0 test report\n",
                },
            )
            violations = mod.check_repository(root)
            self.assertTrue(
                any(v.check_id in {"VERSION-001", "VERSION-002"} for v in violations),
                msg="[DOCS-CONTRACT-VERSION-TEMPLATE] stale 0.2.0 title must fail",
            )


if __name__ == "__main__":
    unittest.main()


def test_public_docs_hygiene_flags_pinned_python(tmp_path: Path) -> None:
    from scripts import check_docs_contract as mod

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bad = docs_dir / "SAMPLE.md"
    bad.write_text("Run `python3.11 scripts/x.py`\n", encoding="utf-8")
    original = mod._tracked_markdown
    mod._tracked_markdown = lambda root: [bad]  # type: ignore[assignment]
    try:
        violations = mod._check_public_docs_hygiene(tmp_path)
    finally:
        mod._tracked_markdown = original
    assert any(item.check_id == "DOCS-PYTHON-001" for item in violations)


def test_public_docs_hygiene_flags_private_path(tmp_path: Path) -> None:
    from scripts import check_docs_contract as mod

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bad = docs_dir / "SAMPLE.md"
    bad.write_text("Workspace lives under ~/code/ forever.\n", encoding="utf-8")
    original = mod._tracked_markdown
    mod._tracked_markdown = lambda root: [bad]  # type: ignore[assignment]
    try:
        violations = mod._check_public_docs_hygiene(tmp_path)
    finally:
        mod._tracked_markdown = original
    assert any(item.check_id == "DOCS-PRIVACY-001" for item in violations)
