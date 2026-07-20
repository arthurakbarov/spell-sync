#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI runner contract and exit-code preservation."""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load_ci_runner():
    spec = importlib.util.spec_from_file_location("ci_runner", ROOT / "scripts" / "ci_runner.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _success_run(mod, argv: list[str], *, cwd=None, env=None) -> tuple[int, str]:
    joined = " ".join(argv)
    if "sys.version_info" in joined:
        return 0, "3.11\n"
    if "pip install" in joined:
        return 0, ""
    if joined.endswith("build"):
        (mod.ROOT / "dist").mkdir(parents=True, exist_ok=True)
        version = mod._package_version()
        (mod.ROOT / "dist" / f"spell_sync-{version}-py3-none-any.whl").write_bytes(b"whl")
        (mod.ROOT / "dist" / f"spell_sync-{version}.tar.gz").write_bytes(b"sdist")
        return 0, ""
    if "twine" in joined:
        return 0, ""
    if "venv" in joined:
        venv_py = Path(argv[-1]) / "bin" / "python"
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("#!/bin/sh\n", encoding="utf-8")
        return 0, ""
    if "spell_sync init" in joined or "spell_sync lint" in joined:
        return 0, ""
    if "spell_sync version" in joined or "spell_sync --help" in joined:
        return 0, ""
    if "pip install -q" in joined and "spell_sync-" in joined:
        return 0, ""
    if "test_gui_smoke.py" in joined:
        return 0, ""
    if "pytest" in joined and "tests/" in joined:
        return 0, ""
    if "-c" in joined and "coverage" in joined:
        (mod.ROOT / "coverage.json").write_text(
            '{"totals":{"missing_lines":[],"num_branches":1,"covered_branches":1}}',
            encoding="utf-8",
        )
        return 0, ""
    if "check-" in joined or "ruff" in joined or "mypy" in joined or "check-docs-style" in joined:
        return 0, ""
    return 0, ""


class TestCiContract(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_ci_runner()

    def test_help_does_not_run_checks(self) -> None:
        with patch.object(self.mod, "CiRunner") as runner_cls:
            with self.assertRaises(SystemExit) as ctx:
                self.mod.main(["--help"])
        runner_cls.assert_not_called()
        self.assertEqual(ctx.exception.code, 0, msg="[CI-CONTRACT-001] --help must exit 0")

    def test_ci_sh_delegates_to_runner(self) -> None:
        text = (ROOT / "scripts" / "ci.sh").read_text(encoding="utf-8")
        self.assertIn(
            "ci_runner.py",
            text,
            msg="[CI-CONTRACT-002] ci.sh must delegate to ci_runner.py",
        )

    def test_first_failure_exit_code_preserved(self) -> None:
        calls: list[list[str]] = []

        def fake_run(argv: list[str], *, cwd=None, env=None):
            calls.append(argv)
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "forced docs.style failure\n"
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        runner = self.mod.CiRunner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-003] expected exit 1")
        summary = json.loads((ROOT / ".artifacts/ci/ci-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["exitCode"], 1)
        self.assertEqual(summary["failedCheckId"], "docs.style")

    def test_ci_failed_id_matches_check(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-contract.py" in joined:
                return 2, "docs contract failed\n"
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        buf = io.StringIO()
        runner = self.mod.CiRunner(run_step=fake_run)
        with patch("sys.stdout", buf):
            rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 2, msg="[CI-CONTRACT-004] expected exit 2")
        self.assertIn("CI_FAILED_ID=docs.contract", buf.getvalue())

    def test_ci_summary_schema(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "fail\n"
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)
        summary = json.loads((ROOT / ".artifacts/ci/ci-summary.json").read_text(encoding="utf-8"))
        for key in (
            "schemaVersion",
            "result",
            "exitCode",
            "startedAt",
            "completedAt",
            "checks",
            "logPath",
        ):
            self.assertIn(key, summary, msg=f"[CI-CONTRACT-005] missing {key}")

    def test_success_final_output(self) -> None:
        buf = io.StringIO()
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod, argv, cwd=cwd, env=env
            ),
        )
        with patch("sys.stdout", buf):
            rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 0, msg="[CI-CONTRACT-006] success exit")
        output = buf.getvalue()
        self.assertIn("CI_RESULT=success", output)
        self.assertIn("CI_EXIT=0", output)
        self.assertIn("CI_SUMMARY=", output)
        self.assertIn("CI_LOG=", output)

    def test_failure_final_output(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "sys.version_info" in " ".join(argv):
                return 1, "unsupported\n"
            return 0, ""

        buf = io.StringIO()
        runner = self.mod.CiRunner(run_step=fake_run)
        with patch("sys.stdout", buf):
            rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1)
        output = buf.getvalue()
        self.assertIn("CI_RESULT=failed", output, msg="[CI-CONTRACT-007] failure banner")
        self.assertIn("CI_FAILED_CHECKS=", output)
        self.assertIn("CI_FAILED_ID=bootstrap.python", output)

    def test_log_and_summary_paths_exist(self) -> None:
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod, argv, cwd=cwd, env=env
            ),
        )
        runner.run(bootstrap=False)
        self.assertTrue(
            (ROOT / ".artifacts/ci/ci.log").is_file(), msg="[CI-CONTRACT-008] ci.log missing"
        )
        self.assertTrue(
            (ROOT / ".artifacts/ci/ci-summary.json").is_file(),
            msg="[CI-CONTRACT-009] ci-summary.json missing",
        )

    def test_retention_keeps_exactly_five(self) -> None:
        artifacts = ROOT / ".artifacts/ci"
        artifacts.mkdir(parents=True, exist_ok=True)
        for idx in range(7):
            (artifacts / f"ci-2026010{idx}T000000Z.log").write_text(
                f"log {idx}\n", encoding="utf-8"
            )
        self.mod._rotate_logs(artifacts)
        self.assertEqual(
            len(list(artifacts.glob("ci-*.log"))), 5, msg="[CI-CONTRACT-010] keep 5 logs"
        )

    def test_timestamp_collision_safe(self) -> None:
        fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod, argv, cwd=cwd, env=env
            ),
            now=lambda: fixed,
        )
        runner.run(bootstrap=False)
        runner.run(bootstrap=False)
        self.assertEqual(
            len(list((ROOT / ".artifacts/ci").glob("ci-20260101T000000Z.log"))),
            1,
            msg="[CI-CONTRACT-011] atomic replace keeps one stamp file",
        )

    def test_venv_failure_stops(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "venv" in joined:
                return 3, "venv failed\n"
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        runner = self.mod.CiRunner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 3, msg="[CI-CONTRACT-012] venv failure must stop")
        failed = [c for c in runner.checks if c["status"] == "failed"]
        self.assertEqual(failed[0]["id"], "packaging.wheel-smoke")

    def test_packaging_paths_expanded_not_literal_glob(self) -> None:
        captured: list[list[str]] = []

        def fake_run(argv: list[str], *, cwd=None, env=None):
            captured.append(argv)
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)
        twine_calls = [argv for argv in captured if "twine" in " ".join(argv)]
        self.assertTrue(twine_calls, msg="[CI-CONTRACT-013] twine must run")
        self.assertNotIn("dist/*", twine_calls[0], msg="[CI-CONTRACT-014] no literal dist/* glob")

    def test_smoke_uses_temporary_home_not_repo_root(self) -> None:
        captured_home: list[str] = []
        init_cwd: list[Path | None] = []

        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "spell_sync init" in joined:
                self.assertIsNotNone(env)
                captured_home.append(env["HOME"])
                init_cwd.append(cwd)
            return _success_run(self.mod, argv, cwd=cwd, env=env)

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)
        self.assertTrue(captured_home, msg="[CI-CONTRACT-015] init smoke must run")
        self.assertTrue(all(path != self.mod.ROOT for path in init_cwd if path is not None))

    def test_cleanup_on_failure(self) -> None:
        (self.mod.ROOT / "coverage.json").write_text("{}", encoding="utf-8")

        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "fail\n"
            return 0, ""

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)
        self.assertFalse(
            (self.mod.ROOT / "coverage.json").exists(), msg="[CI-CONTRACT-016] cleanup coverage"
        )

    def test_no_bootstrap_skips_install(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "pip install" in " ".join(argv):
                raise AssertionError("[CI-CONTRACT-017] bootstrap must be skipped")
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "stop\n"
            return 0, ""

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)

    def test_unsupported_python(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "sys.version_info" in " ".join(argv):
                return 0, "3.10\n"
            return 0, ""

        runner = self.mod.CiRunner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-018] unsupported Python must fail")
        self.assertEqual(runner.checks[0]["id"], "bootstrap.python")

    def test_atomic_summary_replacement(self) -> None:
        summary_path = ROOT / ".artifacts/ci/ci-summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text('{"schemaVersion":1,"result":"failed"}\n', encoding="utf-8")
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod, argv, cwd=cwd, env=env
            ),
        )
        runner.run(bootstrap=False)
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["result"], "success", msg="[CI-CONTRACT-019] summary replaced atomically"
        )


if __name__ == "__main__":
    unittest.main()
