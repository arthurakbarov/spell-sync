#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI runner contract and exit-code preservation."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load_ci_runner():
    spec = importlib.util.spec_from_file_location("ci_runner", ROOT / "scripts" / "ci_runner.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _success_run(root: Path, argv: list[str], *, cwd=None, env=None) -> tuple[int, str]:
    joined = " ".join(argv)
    effective = cwd or root
    if "sys.version_info" in joined:
        return 0, "3.11\n"
    if "pip install" in joined:
        return 0, ""
    if joined.endswith("build"):
        (effective / "dist").mkdir(parents=True, exist_ok=True)
        mod = _load_ci_runner()
        version_text = mod._package_version(root)
        (effective / "dist" / f"spell_sync-{version_text}-py3-none-any.whl").write_bytes(b"whl")
        (effective / "dist" / f"spell_sync-{version_text}.tar.gz").write_bytes(b"sdist")
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
        (effective / "coverage.json").write_text(
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

    def test_ci_sh_uses_python_bin_override(self) -> None:
        text = (ROOT / "scripts" / "ci.sh").read_text(encoding="utf-8")
        self.assertIn("PYTHON_BIN", text, msg="[CI-CONTRACT-002] ci.sh must support PYTHON_BIN")
        self.assertIn("ci_runner.py", text)

    def test_first_failure_exit_code_preserved(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "forced docs.style failure\n"
            return _success_run(self.mod.ROOT, argv, cwd=cwd, env=env)

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
            return _success_run(self.mod.ROOT, argv, cwd=cwd, env=env)

        buf = io.StringIO()
        runner = self.mod.CiRunner(run_step=fake_run)
        with patch("sys.stdout", buf):
            rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 2, msg="[CI-CONTRACT-004] expected exit 2")
        self.assertIn("CI_FAILED_ID=docs.contract", buf.getvalue())

    def test_ci_summary_schema_v2(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            joined = " ".join(argv)
            if "sys.version_info" in joined:
                return 0, "3.11\n"
            if "check-docs-style.sh" in joined:
                return 1, "fail\n"
            return _success_run(self.mod.ROOT, argv, cwd=cwd, env=env)

        self.mod.CiRunner(run_step=fake_run).run(bootstrap=False)
        summary = json.loads((ROOT / ".artifacts/ci/ci-summary.json").read_text(encoding="utf-8"))
        for key in (
            "schemaVersion",
            "runId",
            "result",
            "exitCode",
            "startedAt",
            "completedAt",
            "checks",
            "logPath",
            "historyLogPath",
            "historySummaryPath",
        ):
            self.assertIn(key, summary, msg=f"[CI-CONTRACT-005] missing {key}")
        self.assertEqual(summary["schemaVersion"], 2)

    def test_success_final_output(self) -> None:
        buf = io.StringIO()
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod.ROOT, argv, cwd=cwd, env=env
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
                self.mod.ROOT, argv, cwd=cwd, env=env
            ),
        )
        runner.run(bootstrap=False)
        summary = json.loads((ROOT / ".artifacts/ci/ci-summary.json").read_text(encoding="utf-8"))
        self.assertTrue(Path(summary["logPath"]).is_file(), msg="[CI-CONTRACT-008] ci.log missing")
        self.assertTrue(
            Path(summary["historyLogPath"]).is_file(),
            msg="[CI-CONTRACT-009] history log missing",
        )
        self.assertTrue(
            Path(summary["historySummaryPath"]).is_file(),
            msg="[CI-CONTRACT-010] history summary missing",
        )

    def test_retention_keeps_exactly_five(self) -> None:
        artifacts = ROOT / ".artifacts/ci"
        artifacts.mkdir(parents=True, exist_ok=True)
        for idx in range(7):
            (artifacts / f"ci-run-2026010{idx}T000000.000000Z.log").write_text(
                f"log {idx}\n",
                encoding="utf-8",
            )
        self.mod._rotate_logs(artifacts)
        self.assertEqual(
            len(list(artifacts.glob("ci-run-*.log"))),
            5,
            msg="[CI-CONTRACT-011] keep 5 history logs",
        )

    def test_timestamp_collision_creates_two_history_files(self) -> None:
        fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        runner = self.mod.CiRunner(
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                self.mod.ROOT, argv, cwd=cwd, env=env
            ),
            now=lambda: fixed,
        )
        runner.run(bootstrap=False)
        runner.run(bootstrap=False)
        history = sorted((ROOT / ".artifacts/ci").glob("ci-run-20260101T000000.000000Z*.log"))
        self.assertEqual(len(history), 2, msg="[CI-CONTRACT-012] collision must keep two runs")

    def test_python_310_fails(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "sys.version_info" in " ".join(argv):
                return 0, "3.10\n"
            return 0, ""

        runner = self.mod.CiRunner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-013] Python 3.10 must fail")
        self.assertEqual(runner.checks[0]["id"], "bootstrap.python")

    def test_python_314_passes(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "sys.version_info" in " ".join(argv):
                return 0, "3.14\n"
            return _success_run(self.mod.ROOT, argv, cwd=cwd, env=env)

        runner = self.mod.CiRunner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 0, msg="[CI-CONTRACT-014] Python 3.14 must pass")

    def test_min_python_matches_pyproject(self) -> None:
        minimum = self.mod._min_python_from_pyproject(self.mod.ROOT)
        self.assertEqual(minimum, self.mod.MIN_PYTHON, msg="[CI-CONTRACT-015] metadata minimum")

    def test_custom_root_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            artifacts = root / ".artifacts" / "ci"
            (root / "pyproject.toml").write_text(
                '[project]\nname="x"\nversion="8.8.8"\nrequires-python=">=3.11"\n',
                encoding="utf-8",
            )
            (root / "scripts").mkdir()
            (root / "scripts" / "check-docs-style.sh").write_text("#!/bin/sh\nexit 0\n")
            (root / "scripts" / "check-docs-style.sh").chmod(0o755)
            seen_cwd: list[Path | None] = []

            def fake_run(argv: list[str], *, cwd=None, env=None):
                seen_cwd.append(cwd)
                return _success_run(root, argv, cwd=cwd or root, env=env)

            runner = self.mod.CiRunner(root=root, artifacts=artifacts, run_step=fake_run)
            runner.run(bootstrap=False)
            self.assertEqual(self.mod._package_version(root), "8.8.8")
            self.assertTrue(all(path == root or path is not None for path in seen_cwd))
            self.assertFalse((self.mod.ROOT / "coverage.json").exists())

    def test_internal_failure_records_ci_internal(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if "sys.version_info" in " ".join(argv):
                return 0, "3.11\n"
            raise RuntimeError("injected failure")

        buf = io.StringIO()
        runner = self.mod.CiRunner(run_step=fake_run)
        with patch("sys.stdout", buf):
            rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-016] internal failure exits 1")
        self.assertIn("CI_FAILED_ID=ci.internal", buf.getvalue())

    def test_internal_failure_when_finish_unwritable(self) -> None:
        runner = self.mod.CiRunner()
        runner.started_at = datetime.now(timezone.utc).isoformat()
        runner.artifacts.mkdir(parents=True, exist_ok=True)
        runner._bind_run_artifacts()

        def fail_write(*_args, **_kwargs):
            raise OSError("read-only")

        buf = io.StringIO()
        with patch.object(self.mod, "_atomic_write", side_effect=fail_write):
            with patch("sys.stdout", buf):
                rc = runner._handle_internal_failure(RuntimeError("boom"))
        self.assertEqual(rc, 1)
        self.assertIn("CI_SUMMARY=unavailable", buf.getvalue())
        self.assertIn("CI_LOG=unavailable", buf.getvalue())

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


if __name__ == "__main__":
    unittest.main()
