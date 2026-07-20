#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Documentation contract tests."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_docs_contract():
    spec = importlib.util.spec_from_file_location(
        "check_docs_contract",
        ROOT / "scripts" / "check-docs-contract.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestDocsContract(unittest.TestCase):
    def test_docs_contract_script_passes(self) -> None:
        proc = subprocess.run(
            ["python3.11", "scripts/check-docs-contract.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"[DOCS-CONTRACT-001] docs contract failed:\n{proc.stdout}\n{proc.stderr}",
        )

    def test_validator_has_no_hardcoded_release_version(self) -> None:
        text = (ROOT / "scripts" / "check-docs-contract.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "version must be 0.2.1",
            text,
            msg="[DOCS-CONTRACT-002] validator must not hardcode release version",
        )
        self.assertNotIn(
            "Phase 3 must not be started",
            text,
            msg="[DOCS-CONTRACT-003] validator must not hardcode phase gate text",
        )
        self.assertIn(
            "tomllib",
            text,
            msg="[DOCS-CONTRACT-004] version must come from pyproject.toml",
        )

    def test_line_historical_context_uses_line_window(self) -> None:
        mod = _load_docs_contract()
        lines = [
            "Historical context: removed API",
            "allow_new_project_wizard was removed",
        ]
        self.assertTrue(
            mod._line_has_historical_context(lines, 1),
            msg="[DOCS-CONTRACT-005] historical marker in window",
        )
        self.assertFalse(
            mod._line_has_historical_context(["allow_new_project_wizard active"], 0),
            msg="[DOCS-CONTRACT-006] stale API without context fails",
        )

    def test_project_version_read_from_pyproject(self) -> None:
        mod = _load_docs_contract()
        version = mod._project_version()
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            f'version = "{version}"', pyproject, msg="[DOCS-CONTRACT-007] semver from pyproject"
        )

    def test_stale_version_detection_uses_current_version(self) -> None:
        mod = _load_docs_contract()
        version = mod._project_version()
        self.assertNotEqual(version, "0.2.0")
        errors = mod._check_stale_version_claims(version)
        self.assertEqual(errors, 0, msg="[DOCS-CONTRACT-008] current docs must not claim 0.2.0")


if __name__ == "__main__":
    unittest.main()
