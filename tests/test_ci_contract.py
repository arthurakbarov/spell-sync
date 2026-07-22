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
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

MINIMAL_PYPROJECT = '[project]\nname="spell-sync"\nversion="1.2.3"\nrequires-python=">=3.11"\n'


def _load_ci_runner():
    spec = importlib.util.spec_from_file_location("ci_runner", ROOT / "scripts" / "ci_runner.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def command_tail(argv: Sequence[str]) -> tuple[str, ...]:
    return tuple(argv[1:])


def _is_python_version_probe(argv: list[str]) -> bool:
    return len(argv) >= 3 and argv[1] == "-c" and "sys.version_info" in argv[2]


def _is_pip_install(argv: list[str]) -> bool:
    return len(argv) >= 4 and list(argv[1:4]) == ["-m", "pip", "install"]


def _is_build(argv: list[str]) -> bool:
    return len(argv) >= 3 and list(argv[1:3]) == ["-m", "build"]


def _is_venv_create(argv: list[str]) -> bool:
    return len(argv) >= 4 and list(argv[1:3]) == ["-m", "venv"]


def _is_twine(argv: list[str]) -> bool:
    return len(argv) >= 3 and list(argv[1:3]) == ["-m", "twine"]


def _is_coverage_gate(argv: list[str]) -> bool:
    return len(argv) >= 3 and argv[1] == "-c" and "coverage.json" in argv[2]


def _is_wheel_origin_probe(argv: list[str]) -> bool:
    return (
        len(argv) >= 4 and argv[1] == "-c" and "json.dumps" in argv[2] and "spell_sync" in argv[2]
    )


def _seed_execution_control(root: Path) -> None:
    import shutil

    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    budget = ROOT / "tests" / "execution-budget.toml"
    if budget.is_file():
        (tests_dir / "execution-budget.toml").write_text(
            budget.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    execution_control_src = ROOT / "scripts" / "execution_control"
    if execution_control_src.is_dir():
        dest = root / "scripts" / "execution_control"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(execution_control_src, dest)
    for script in (
        "validate_execution_budget.py",
        "check-ci-necessity.py",
        "check-ci-evidence.py",
        "ci_input_state.py",
        "documentation_state.py",
    ):
        source = ROOT / "scripts" / script
        if source.is_file():
            (root / "scripts" / script).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
    ci_impact_src = ROOT / "scripts" / "ci_impact"
    if ci_impact_src.is_dir():
        dest = root / "scripts" / "ci_impact"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ci_impact_src, dest)


def _make_test_root(tmp: Path) -> tuple[Path, Path]:
    root = tmp / "repo"
    root.mkdir()
    artifacts = root / ".artifacts" / "ci"
    (root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "check-docs-style.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "scripts" / "check-docs-style.sh").chmod(0o755)
    for name in (
        "check-docs-contract.py",
        "check-agent-config.py",
        "check-target-capabilities.py",
        "validate_test_impact.py",
        "validate_ci_impact.py",
        "validate_execution_budget.py",
    ):
        (root / "scripts" / name).write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    _seed_execution_control(root)
    ci_dir = root / "ci"
    ci_dir.mkdir()
    source_registry = ROOT / "ci" / "ci-impact.toml"
    if source_registry.is_file():
        (ci_dir / "ci-impact.toml").write_text(
            source_registry.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        (ci_dir / "ci-impact.toml").write_text(
            "schemaVersion = 1\n[classes.product]\npatterns = []\n", encoding="utf-8"
        )
    return root, artifacts


def _argv_text(argv: list[str]) -> str:
    return " ".join(str(part) for part in argv)


def _is_validator_script(argv: list[str]) -> bool:
    text = _argv_text(argv)
    return any(
        marker in text
        for marker in (
            "check-docs-style.sh",
            "check-docs-contract.py",
            "check-agent-config.py",
            "check-target-capabilities.py",
            "validate_test_impact.py",
            "validate_ci_impact.py",
            "validate_execution_budget.py",
        )
    )


def _success_run(
    root: Path,
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    python_version: str = "3.11",
    wheel_origin: str | None = None,
) -> tuple[int, str]:
    effective = cwd or root
    if _is_python_version_probe(argv):
        return 0, f"{python_version}\n"
    if _is_pip_install(argv):
        return 0, ""
    if _is_build(argv):
        (effective / "dist").mkdir(parents=True, exist_ok=True)
        mod = _load_ci_runner()
        version_text = mod._package_version(root)
        (effective / "dist" / f"spell_sync-{version_text}-py3-none-any.whl").write_bytes(b"whl")
        (effective / "dist" / f"spell_sync-{version_text}.tar.gz").write_bytes(b"sdist")
        return 0, ""
    if _is_twine(argv):
        return 0, ""
    if _is_venv_create(argv):
        venv_py = Path(argv[-1]) / "bin" / "python"
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("#!/bin/sh\n", encoding="utf-8")
        return 0, ""
    if _is_wheel_origin_probe(argv):
        default_origin = (
            Path(argv[0]).resolve().parent.parent / "site-packages" / "spell_sync" / "__init__.py"
        )
        origin = wheel_origin or str(default_origin)
        mod = _load_ci_runner()
        version_text = mod._package_version(root)
        payload = {
            "origin": origin,
            "metadataVersion": version_text,
            "sysPrefix": str(Path(argv[0]).resolve().parent.parent.parent),
            "basePrefix": str(Path(argv[0]).resolve().parent.parent.parent),
            "sysExecutable": str(argv[0]),
        }
        result_path = Path(argv[3])
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        return 0, ""
    tail = command_tail(argv)
    if tail[:2] == ("-m", "spell_sync"):
        sub = tail[2:]
        if sub and sub[0] in {"version", "init", "lint"}:
            return 0, ""
        if sub == ("--help",) or sub == ("support-report", "--format", "json"):
            return 0, ""
    if tail[:2] == ("-m", "pytest"):
        if "test_gui_smoke.py" in argv or "tests/" in argv:
            return 0, ""
    if _is_coverage_gate(argv):
        (effective / "coverage.json").write_text(
            '{"totals":{"missing_lines":[],"num_branches":1,"covered_branches":1}}',
            encoding="utf-8",
        )
        return 0, ""
    if _is_validator_script(argv):
        return 0, ""
    if tail[:2] == ("-m", "ruff") or tail[:2] == ("-m", "mypy"):
        return 0, ""
    return 0, ""


class TestCiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._real_artifacts_snapshot = (
            {p.name for p in (ROOT / ".artifacts" / "ci").iterdir()}
            if (ROOT / ".artifacts" / "ci").is_dir()
            else set()
        )

    def setUp(self) -> None:
        self.mod = _load_ci_runner()
        self._tmp = tempfile.TemporaryDirectory()
        self.root, self.artifacts = _make_test_root(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()
        real_artifacts = ROOT / ".artifacts" / "ci"
        if real_artifacts.is_dir():
            after = {p.name for p in real_artifacts.iterdir()}
            self.assertEqual(
                self._real_artifacts_snapshot,
                after,
                msg="real checkout .artifacts/ci must not change",
            )

    def _runner(self, **kwargs):
        defaults = {
            "root": self.root,
            "artifacts": self.artifacts,
            "run_step": lambda argv, *, cwd=None, env=None: _success_run(
                self.root, argv, cwd=cwd or self.root, env=env
            ),
        }
        defaults.update(kwargs)
        return self.mod.CiRunner(**defaults)

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
            if _is_python_version_probe(argv):
                return 0, "3.11\n"
            if "check-docs-style.sh" in _argv_text(argv):
                return 1, "forced docs.style failure\n"
            return _success_run(self.root, argv, cwd=cwd or self.root, env=env)

        rc = self._runner(run_step=fake_run).run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-003] expected exit 1")
        summary = json.loads((self.artifacts / "ci-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["exitCode"], 1)
        self.assertEqual(summary["failedCheckId"], "docs.style")

    def test_ci_failed_id_matches_check(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_python_version_probe(argv):
                return 0, "3.11\n"
            if "check-docs-contract.py" in _argv_text(argv):
                return 2, "docs contract failed\n"
            return _success_run(self.root, argv, cwd=cwd or self.root, env=env)

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = self._runner(run_step=fake_run).run(bootstrap=False)
        self.assertEqual(rc, 2, msg="[CI-CONTRACT-004] expected exit 2")
        self.assertIn("CI_FAILED_ID=docs.contract", buf.getvalue())

    def test_ci_summary_schema_v2(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_python_version_probe(argv):
                return 0, "3.11\n"
            if "check-docs-style.sh" in _argv_text(argv):
                return 1, "fail\n"
            return _success_run(self.root, argv, cwd=cwd or self.root, env=env)

        self._runner(run_step=fake_run).run(bootstrap=False)
        summary = json.loads((self.artifacts / "ci-summary.json").read_text(encoding="utf-8"))
        for key in (
            "schemaVersion",
            "runId",
            "result",
            "exitCode",
            "startedAt",
            "completedAt",
            "mode",
            "finalEvidence",
            "treeDigest",
            "ciInputDigest",
            "gitHeadAtRun",
            "evidenceScope",
            "checks",
            "logPath",
            "historyLogPath",
            "historySummaryPath",
        ):
            self.assertIn(key, summary, msg=f"[CI-CONTRACT-005] missing {key}")
        self.assertEqual(summary["schemaVersion"], 4)

    def test_success_final_output(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = self._runner(python_bin="/opt/pyvenv/bin/python").run(bootstrap=False)
        self.assertEqual(rc, 0, msg="[CI-CONTRACT-006] success exit")
        output = buf.getvalue()
        self.assertIn("CI_RESULT=success", output)
        self.assertIn("CI_EXIT=0", output)
        self.assertIn("CI_SUMMARY=", output)
        self.assertIn("CI_LOG=", output)

    def test_failure_final_output(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_python_version_probe(argv):
                return 1, "unsupported\n"
            return 0, ""

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = self._runner(run_step=fake_run).run(bootstrap=False)
        self.assertEqual(rc, 1)
        output = buf.getvalue()
        self.assertIn("CI_RESULT=failed", output, msg="[CI-CONTRACT-007] failure banner")
        self.assertIn("CI_FAILED_CHECKS=", output)
        self.assertIn("CI_FAILED_ID=bootstrap.python", output)

    def test_log_and_summary_paths_exist(self) -> None:
        self._runner().run(bootstrap=False)
        summary = json.loads((self.artifacts / "ci-summary.json").read_text(encoding="utf-8"))
        self.assertTrue(Path(summary["logPath"]).is_file(), msg="[CI-CONTRACT-008] ci.log missing")
        self.assertTrue(
            Path(summary["historyLogPath"]).is_file(),
            msg="[CI-CONTRACT-009] history log missing",
        )
        self.assertTrue(
            Path(summary["historySummaryPath"]).is_file(),
            msg="[CI-CONTRACT-010] history summary missing",
        )

    def test_retention_keeps_exactly_five_pairs(self) -> None:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        for idx in range(7):
            run_id = f"2026010{idx}T000000.000000Z"
            (self.artifacts / f"ci-run-{run_id}.log").write_text(f"log {idx}\n", encoding="utf-8")
            (self.artifacts / f"ci-summary-{run_id}.json").write_text("{}", encoding="utf-8")
        self.mod._rotate_completed_pairs(self.artifacts)
        self.assertEqual(len(list(self.artifacts.glob("ci-run-*.log"))), 5)
        self.assertEqual(len(list(self.artifacts.glob("ci-summary-*.json"))), 5)

    def test_timestamp_collision_creates_two_history_files(self) -> None:
        fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        def make_runner():
            return self._runner(now=lambda: fixed)

        make_runner().run(bootstrap=False)
        make_runner().run(bootstrap=False)
        history = sorted(self.artifacts.glob("ci-run-20260101T000000.000000Z*.log"))
        self.assertEqual(len(history), 2, msg="[CI-CONTRACT-012] collision must keep two runs")

    def test_python_310_fails(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_python_version_probe(argv):
                return 0, "3.10\n"
            return 0, ""

        runner = self._runner(run_step=fake_run)
        rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-013] Python 3.10 must fail")
        self.assertEqual(runner.checks[0]["id"], "bootstrap.python")

    def test_python_314_passes_with_pyvenv_interpreter(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            return _success_run(
                self.root,
                argv,
                cwd=cwd or self.root,
                env=env,
                python_version="3.14",
            )

        rc = self._runner(
            run_step=fake_run,
            python_bin="/opt/pyvenv/bin/python",
        ).run(bootstrap=False)
        self.assertEqual(rc, 0, msg="[CI-CONTRACT-014] Python 3.14 must pass")

    def test_interpreter_path_with_venv_does_not_trigger_fake_venv(self) -> None:
        calls: list[list[str]] = []

        def fake_run(argv: list[str], *, cwd=None, env=None):
            calls.append(list(argv))
            return _success_run(
                self.root,
                argv,
                cwd=cwd or self.root,
                env=env,
                python_version="3.13",
            )

        self._runner(
            run_step=fake_run,
            python_bin="/opt/pyvenv/bin/python",
        ).run(bootstrap=False)
        self.assertTrue(any(_is_venv_create(argv) for argv in calls))

    def test_interpreter_path_with_build_does_not_trigger_fake_build(self) -> None:
        rc = self._runner(python_bin="/tmp/build-tools/python").run(bootstrap=False)
        self.assertEqual(rc, 0)

    def test_repository_path_with_pip_does_not_trigger_fake_pip(self) -> None:
        pip_root = self.root / "my-pip-tools"
        pip_root.mkdir()
        (pip_root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
        ci_dir = pip_root / "ci"
        ci_dir.mkdir()
        (ci_dir / "ci-impact.toml").write_text(
            (ROOT / "ci" / "ci-impact.toml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (pip_root / "scripts").mkdir()
        for name in (
            "check-docs-style.sh",
            "check-docs-contract.py",
            "check-agent-config.py",
            "check-target-capabilities.py",
            "validate_test_impact.py",
            "validate_ci_impact.py",
        ):
            target = pip_root / "scripts" / name
            if name.endswith(".sh"):
                target.write_text("#!/bin/sh\nexit 0\n")
                target.chmod(0o755)
            else:
                target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        _seed_execution_control(pip_root)
        artifacts = pip_root / ".artifacts" / "ci"
        rc = self.mod.CiRunner(
            root=pip_root,
            artifacts=artifacts,
            run_step=lambda argv, *, cwd=None, env=None: _success_run(
                pip_root, argv, cwd=cwd or pip_root, env=env
            ),
        ).run(bootstrap=False)
        self.assertEqual(rc, 0)

    def test_min_python_matches_pyproject(self) -> None:
        minimum = self.mod._min_python_from_pyproject(self.root)
        self.assertEqual(minimum, self.mod.MIN_PYTHON, msg="[CI-CONTRACT-015] metadata minimum")

    def test_custom_root_isolation(self) -> None:
        coverage_json = ROOT / "coverage.json"
        previous_coverage = coverage_json.read_bytes() if coverage_json.is_file() else None
        coverage_json.unlink(missing_ok=True)
        try:
            seen_cwd: list[Path | None] = []

            def fake_run(argv: list[str], *, cwd=None, env=None):
                seen_cwd.append(cwd)
                return _success_run(self.root, argv, cwd=cwd or self.root, env=env)

            self._runner(run_step=fake_run).run(bootstrap=False)
            self.assertEqual(self.mod._package_version(self.root), "1.2.3")
            self.assertTrue(all(path == self.root or path is not None for path in seen_cwd))
            self.assertFalse(coverage_json.exists())
        finally:
            if previous_coverage is not None:
                coverage_json.write_bytes(previous_coverage)
            else:
                coverage_json.unlink(missing_ok=True)

    def test_internal_failure_records_ci_internal(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_python_version_probe(argv):
                return 0, "3.11\n"
            raise RuntimeError("injected failure")

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = self._runner(run_step=fake_run).run(bootstrap=False)
        self.assertEqual(rc, 1, msg="[CI-CONTRACT-016] internal failure exits 1")
        self.assertIn("CI_FAILED_ID=ci.internal", buf.getvalue())

    def test_internal_failure_when_finish_unwritable(self) -> None:
        runner = self._runner()
        runner.started_at = datetime.now(timezone.utc).isoformat()
        runner.artifacts.mkdir(parents=True, exist_ok=True)
        runner._bind_run_artifacts()
        runner._artifacts_ready = True
        runner._used = True

        def fail_write(*_args, **_kwargs):
            raise OSError("read-only")

        buf = io.StringIO()
        with patch.object(self.mod, "_atomic_write", side_effect=fail_write):
            with patch("sys.stdout", buf):
                rc = runner._handle_internal_failure(RuntimeError("boom"))
        self.assertEqual(rc, 1)
        self.assertIn("CI_SUMMARY=unavailable", buf.getvalue())
        self.assertIn("CI_LOG=unavailable", buf.getvalue())

    def test_internal_failure_on_artifacts_mkdir(self) -> None:
        runner = self._runner()

        def fail_mkdir(*_args, **_kwargs):
            raise OSError("artifacts unavailable")

        buf = io.StringIO()
        with patch.object(Path, "mkdir", side_effect=fail_mkdir):
            with patch("sys.stdout", buf):
                rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1)
        self.assertIn("CI_SUMMARY=unavailable", buf.getvalue())

    def test_internal_failure_on_bind_run_artifacts(self) -> None:
        runner = self._runner()
        with patch.object(runner, "_bind_run_artifacts", side_effect=RuntimeError("bind failed")):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1)
        self.assertIn("CI_FAILED_ID=ci.internal", buf.getvalue())

    def test_internal_failure_on_min_python_from_pyproject(self) -> None:
        runner = self._runner()
        with patch.object(
            self.mod,
            "_min_python_from_pyproject",
            side_effect=RuntimeError("parse failed"),
        ):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = runner.run(bootstrap=False)
        self.assertEqual(rc, 1)
        self.assertIn("CI_FAILED_ID=ci.internal", buf.getvalue())

    def test_internal_failure_on_malformed_pyproject(self) -> None:
        (self.root / "pyproject.toml").write_text("not valid toml [[", encoding="utf-8")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = self._runner().run(bootstrap=False)
        self.assertEqual(rc, 1)
        self.assertIn("CI_FAILED_ID=ci.internal", buf.getvalue())

    def test_no_bootstrap_skips_install(self) -> None:
        def fake_run(argv: list[str], *, cwd=None, env=None):
            if _is_pip_install(argv):
                raise AssertionError("[CI-CONTRACT-017] bootstrap must be skipped")
            if _is_python_version_probe(argv):
                return 0, "3.11\n"
            if "check-docs-style.sh" in _argv_text(argv):
                return 1, "stop\n"
            return 0, ""

        self._runner(run_step=fake_run).run(bootstrap=False)

    def test_runner_is_one_shot(self) -> None:
        runner = self._runner()
        runner.run(bootstrap=False)
        with self.assertRaises(RuntimeError):
            runner.run(bootstrap=False)

    def test_run_id_collision_with_existing_summary_only(self) -> None:
        fixed = datetime(2026, 2, 2, 0, 0, 0, tzinfo=timezone.utc)
        run_id = "20260202T000000.000000Z"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / f"ci-summary-{run_id}.json").write_text("{}", encoding="utf-8")
        runner = self._runner(now=lambda: fixed)
        runner.run(bootstrap=False)
        self.assertFalse((self.artifacts / f"ci-run-{run_id}.log").exists())
        self.assertTrue((self.artifacts / f"ci-run-{run_id}-01.log").exists())

    def test_run_id_collision_with_existing_log_only(self) -> None:
        fixed = datetime(2026, 2, 3, 0, 0, 0, tzinfo=timezone.utc)
        run_id = "20260203T000000.000000Z"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / f"ci-run-{run_id}.log").write_text("orphan\n", encoding="utf-8")
        runner = self._runner(now=lambda: fixed)
        runner.run(bootstrap=False)
        self.assertTrue((self.artifacts / f"ci-run-{run_id}-01.log").exists())

    def test_orphan_log_removed_after_successful_run(self) -> None:
        orphan_id = "20260101T000000.000000Z"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / f"ci-run-{orphan_id}.log").write_text("orphan\n", encoding="utf-8")
        self._runner().run(bootstrap=False)
        self.assertFalse((self.artifacts / f"ci-run-{orphan_id}.log").exists())

    def test_orphan_summary_removed_after_successful_run(self) -> None:
        orphan_id = "20260102T000000.000000Z"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / f"ci-summary-{orphan_id}.json").write_text("{}", encoding="utf-8")
        self._runner().run(bootstrap=False)
        self.assertFalse((self.artifacts / f"ci-summary-{orphan_id}.json").exists())

    def test_touched_old_log_does_not_break_pair_retention(self) -> None:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        kept_id = "20260103T000000.000000Z"
        drop_id = "20260104T000000.000000Z"
        for run_id in (kept_id, drop_id):
            (self.artifacts / f"ci-run-{run_id}.log").write_text("log\n", encoding="utf-8")
            (self.artifacts / f"ci-summary-{run_id}.json").write_text("{}", encoding="utf-8")
        old_log = self.artifacts / f"ci-run-{drop_id}.log"
        old_log.touch()
        for idx in range(5):
            run_id = f"2026011{idx}T000000.000000Z"
            (self.artifacts / f"ci-run-{run_id}.log").write_text("log\n", encoding="utf-8")
            (self.artifacts / f"ci-summary-{run_id}.json").write_text("{}", encoding="utf-8")
        self.mod._rotate_completed_pairs(self.artifacts, keep=5)
        remaining = {self.mod._run_id_from_log(p) for p in self.artifacts.glob("ci-run-*.log")}
        self.assertNotIn(drop_id, remaining)
        self.assertIn("20260114T000000.000000Z", remaining)

    def test_wheel_smoke_runs_outside_checkout(self) -> None:
        seen_cwd: list[Path] = []

        def fake_run(argv: list[str], *, cwd=None, env=None):
            if cwd is not None:
                seen_cwd.append(Path(cwd))
            return _success_run(self.root, argv, cwd=cwd or self.root, env=env)

        self._runner(run_step=fake_run).run(bootstrap=False)
        outside = [path for path in seen_cwd if path.name == "outside-checkout"]
        self.assertTrue(outside)
        self.assertTrue(all(self.root not in path.parents for path in outside))

    def test_wheel_smoke_detects_checkout_shadowing(self) -> None:
        checkout_origin = str(self.root / "spell_sync" / "__init__.py")

        def fake_run(argv: list[str], *, cwd=None, env=None):
            return _success_run(
                self.root,
                argv,
                cwd=cwd or self.root,
                env=env,
                wheel_origin=checkout_origin,
            )

        rc = self._runner(run_step=fake_run).run(bootstrap=False)
        self.assertEqual(rc, 1)
        summary = json.loads((self.artifacts / "ci-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["failedCheckId"], "packaging.wheel-smoke")

    def test_six_runs_keep_five_complete_pairs(self) -> None:
        fixed = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        counter = {"n": 0}

        def clock():
            counter["n"] += 1
            return fixed.replace(second=counter["n"] % 60)

        for _ in range(6):
            self._runner(now=clock).run(bootstrap=False)
        logs = sorted(self.artifacts.glob("ci-run-*.log"), key=lambda p: p.name)
        summaries = sorted(self.artifacts.glob("ci-summary-*.json"), key=lambda p: p.name)
        self.assertEqual(len(logs), 5)
        self.assertEqual(len(summaries), 5)
        log_ids = {self.mod._run_id_from_log(p) for p in logs}
        summary_ids = {self.mod._run_id_from_summary(p) for p in summaries}
        self.assertEqual(log_ids, summary_ids)
        current = json.loads((self.artifacts / "ci-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(current["historyLogPath"]).name, logs[-1].name)
        self.assertEqual(Path(current["historySummaryPath"]).name, summaries[-1].name)


if __name__ == "__main__":
    unittest.main()
