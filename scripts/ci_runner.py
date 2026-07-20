#!/usr/bin/env python3
"""CI orchestrator: non-interactive checks, log retention, machine-readable summary."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "ci"
LOG_RETENTION = 5
SUMMARY_SCHEMA = 2
MIN_PYTHON = (3, 11)
INTERNAL_CHECK_ID = "ci.internal"

RunStep = Callable[..., tuple[int, str]]


def _run_step(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    chunk = proc.stdout
    if proc.stderr:
        if chunk and not chunk.endswith("\n"):
            chunk += "\n"
        chunk += proc.stderr
    return proc.returncode, chunk


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _rotate_timestamped(artifacts: Path, pattern: str, *, keep: int) -> None:
    files = sorted(artifacts.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def _rotate_logs(artifacts: Path) -> None:
    _rotate_timestamped(artifacts, "ci-run-*.log", keep=LOG_RETENTION)
    _rotate_timestamped(artifacts, "ci-summary-*.json", keep=LOG_RETENTION)


def _min_python_from_pyproject(root: Path) -> tuple[int, int]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    requires = data.get("project", {}).get("requires-python")
    if not isinstance(requires, str):
        return MIN_PYTHON
    match = re.search(r"(?:>=|==)\s*(\d+)\.(\d+)", requires)
    if not match:
        return MIN_PYTHON
    return int(match.group(1)), int(match.group(2))


def _python_version_tuple(version_text: str) -> tuple[int, int] | None:
    parts = version_text.strip().split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def _python_version_ok(version_text: str, minimum: tuple[int, int]) -> bool:
    parsed = _python_version_tuple(version_text)
    return parsed is not None and parsed >= minimum


def _package_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise RuntimeError("pyproject.toml missing project.version")
    return version


def _coverage_gate(
    py: str,
    *,
    root: Path,
    run_step: RunStep,
) -> tuple[int, str]:
    script = """
import json
totals = json.load(open("coverage.json", encoding="utf-8"))["totals"]
if totals["missing_lines"]:
    raise SystemExit(f"line coverage must be 100% ({totals['missing_lines']} lines missing)")
branches = totals["num_branches"]
branch_rate = 100.0 if not branches else 100.0 * totals["covered_branches"] / branches
if branch_rate < 96:
    raise SystemExit(f"branch coverage must be at least 96% ({branch_rate:.2f}%)")
print(f"coverage policy: 100% lines, {branch_rate:.2f}% branches")
"""
    return run_step([py, "-c", script], cwd=root)


def _make_run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S") + f".{now.microsecond:06d}Z"


def _unique_run_id(artifacts: Path, now: datetime) -> str:
    base = _make_run_id(now)
    candidate = base
    suffix = 0
    while (artifacts / f"ci-run-{candidate}.log").exists():
        suffix += 1
        candidate = f"{base}-{suffix:02d}"
    return candidate


class CiRunner:
    def __init__(
        self,
        *,
        root: Path = ROOT,
        artifacts: Path | None = None,
        run_step: RunStep | None = None,
        now: Callable[[], datetime] | None = None,
        python_bin: str | None = None,
    ) -> None:
        self.root = root
        self.artifacts = artifacts if artifacts is not None else root / ".artifacts" / "ci"
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.python_bin = python_bin or sys.executable
        if run_step is None:
            root_ref = self.root

            def bound_run_step(
                argv: list[str],
                *,
                cwd: Path | None = None,
                env: dict[str, str] | None = None,
            ) -> tuple[int, str]:
                return _run_step(argv, cwd=cwd or root_ref, env=env)

            self.run_step = bound_run_step
        else:
            self.run_step = run_step
        self.checks: list[dict[str, object]] = []
        self.log_lines: list[str] = []
        self.cleanup_paths: list[Path] = []
        self.started_at = ""
        self.run_id = ""
        self._log_path = Path()
        self._summary_path = Path()
        self._history_log_path = Path()
        self._history_summary_path = Path()

    def _bind_run_artifacts(self) -> None:
        self.run_id = _unique_run_id(self.artifacts, self.now())
        self._log_path = (self.artifacts / "ci.log").resolve()
        self._summary_path = (self.artifacts / "ci-summary.json").resolve()
        self._history_log_path = (self.artifacts / f"ci-run-{self.run_id}.log").resolve()
        self._history_summary_path = (self.artifacts / f"ci-summary-{self.run_id}.json").resolve()

    def _finish(self, exit_code: int) -> int:
        return self.finish(exit_code)

    def record(self, step_id: str, rc: int, output: str, summary: str = "") -> None:
        self.checks.append(
            {
                "id": step_id,
                "status": "passed" if rc == 0 else "failed",
                "exitCode": rc,
                **({"summary": summary} if summary else {}),
            }
        )
        self.log_lines.append(f"=== {step_id} exit={rc} ===")
        self.log_lines.append(output.rstrip())
        self.log_lines.append("")
        if output:
            sys.stdout.write(output if output.endswith("\n") else output + "\n")
            sys.stdout.flush()

    def _fail_summary(self, step_id: str, output: str) -> str:
        for line in output.splitlines():
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                return line.strip()
        if output.strip():
            return output.strip().splitlines()[-1]
        return f"{step_id} failed"

    def _print_failure_block(
        self,
        exit_code: int,
        *,
        summary_path: str,
        log_path: str,
        failed_checks: int = 0,
        failed_id: str = "",
    ) -> None:
        print(f"CI_RESULT={'success' if exit_code == 0 else 'failed'}")
        print(f"CI_EXIT={exit_code}")
        if failed_checks:
            print(f"CI_FAILED_CHECKS={failed_checks}")
        if failed_id:
            print(f"CI_FAILED_ID={failed_id}")
        print(f"CI_SUMMARY={summary_path}")
        print(f"CI_LOG={log_path}")

    def finish(self, exit_code: int) -> int:
        failed = sum(1 for c in self.checks if c["status"] == "failed")
        failed_id = next((str(c["id"]) for c in self.checks if c["status"] == "failed"), "")
        completed = self.now().isoformat()
        payload = {
            "schemaVersion": SUMMARY_SCHEMA,
            "runId": self.run_id,
            "result": "success" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "startedAt": self.started_at,
            "completedAt": completed,
            "checks": self.checks,
            "logPath": str(self._log_path),
            "historyLogPath": str(self._history_log_path),
            "historySummaryPath": str(self._history_summary_path),
        }
        if failed_id:
            payload["failedCheckId"] = failed_id
        text = "\n".join(self.log_lines) + "\n"
        _atomic_write(self._log_path, text)
        _atomic_write(self._history_log_path, text)
        summary_text = json.dumps(payload, indent=2) + "\n"
        _atomic_write(self._summary_path, summary_text)
        _atomic_write(self._history_summary_path, summary_text)
        _rotate_logs(self.artifacts)
        self._print_failure_block(
            exit_code,
            summary_path=str(self._summary_path),
            log_path=str(self._log_path),
            failed_checks=failed,
            failed_id=failed_id,
        )
        return exit_code

    def _handle_internal_failure(self, exc: BaseException) -> int:
        if isinstance(exc, KeyboardInterrupt):
            raise exc
        detail = f"{type(exc).__name__}: {exc}"
        self.log_lines.append(f"=== {INTERNAL_CHECK_ID} internal error ===")
        self.log_lines.append(detail)
        self.log_lines.append(traceback.format_exc())
        self.record(INTERNAL_CHECK_ID, 1, detail)
        try:
            return self.finish(1)
        except Exception:
            self._print_failure_block(
                1,
                summary_path="unavailable",
                log_path="unavailable",
                failed_checks=1,
                failed_id=INTERNAL_CHECK_ID,
            )
            return 1

    def _cleanup(self) -> None:
        try:
            (self.root / "coverage.json").unlink(missing_ok=True)
            for path in self.cleanup_paths:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            shutil.rmtree(self.root / "build", ignore_errors=True)
            shutil.rmtree(self.root / "dist", ignore_errors=True)
            shutil.rmtree(self.root / "spell_sync.egg-info", ignore_errors=True)
        except Exception:
            pass

    def run(self, *, bootstrap: bool = True) -> int:
        self.started_at = self.now().isoformat()
        py = self.python_bin
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self._bind_run_artifacts()
        minimum = _min_python_from_pyproject(self.root)

        try:
            pyver_rc, pyver_out = self.run_step(
                [py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                cwd=self.root,
            )
            pyver = pyver_out.strip().splitlines()[-1] if pyver_out.strip() else ""
            if pyver_rc != 0 or not _python_version_ok(pyver, minimum):
                detail = (
                    pyver_out.strip()
                    or f"unsupported Python {pyver!r} via {py} (need>={minimum[0]}.{minimum[1]})"
                )
                self.record("bootstrap.python", 1, detail)
                return self._finish(1)
            self.record("bootstrap.python", 0, f"python {pyver} via {py}")

            if bootstrap:
                install_rc, install_out = self.run_step(
                    [
                        py,
                        "-m",
                        "pip",
                        "install",
                        "-q",
                        "ruff",
                        "mypy",
                        "pytest",
                        "pytest-cov",
                        "build",
                        "wheel",
                        "twine",
                        "setuptools>=77",
                    ],
                    cwd=self.root,
                )
                self.record("deps.install", install_rc, install_out)
                if install_rc != 0:
                    return self._finish(install_rc)

                install_editable_rc, install_editable_out = self.run_step(
                    [py, "-m", "pip", "install", "-q", "-e", "."],
                    cwd=self.root,
                )
                self.record("deps.editable", install_editable_rc, install_editable_out)
                if install_editable_rc != 0:
                    return self._finish(install_editable_rc)

            steps: list[tuple[str, list[str]]] = [
                ("docs.style", ["bash", "scripts/check-docs-style.sh"]),
                ("docs.contract", [py, "scripts/check-docs-contract.py"]),
                ("agent.config", [py, "scripts/check-agent-config.py"]),
                ("targets.capabilities", [py, "scripts/check-target-capabilities.py", "--check"]),
                ("ruff.check", [py, "-m", "ruff", "check", "spell_sync", "tests", "scripts"]),
                (
                    "ruff.format",
                    [py, "-m", "ruff", "format", "--check", "spell_sync", "tests", "scripts"],
                ),
                ("mypy", [py, "-m", "mypy", "spell_sync"]),
                (
                    "tests.pytest",
                    [
                        py,
                        "-m",
                        "pytest",
                        "tests/",
                        "-q",
                        "--cov=spell_sync",
                        "--cov-branch",
                        "--cov-report=term-missing:skip-covered",
                        "--cov-report=json",
                        "--cov-fail-under=98",
                    ],
                ),
            ]

            for step_id, argv in steps:
                rc, out = self.run_step(argv, cwd=self.root)
                summary = self._fail_summary(step_id, out) if rc != 0 else ""
                self.record(step_id, rc, out, summary)
                if rc != 0:
                    return self._finish(rc)

            cov_rc, cov_out = _coverage_gate(py, root=self.root, run_step=self.run_step)
            self.record("coverage.policy", cov_rc, cov_out)
            if cov_rc != 0:
                return self._finish(cov_rc)

            shutil.rmtree(self.root / "build", ignore_errors=True)
            shutil.rmtree(self.root / "dist", ignore_errors=True)
            shutil.rmtree(self.root / "spell_sync.egg-info", ignore_errors=True)
            build_rc, build_out = self.run_step([py, "-m", "build"], cwd=self.root)
            self.record("packaging.build", build_rc, build_out)
            if build_rc != 0:
                return self._finish(build_rc)

            dist = self.root / "dist"
            dist_artifacts = sorted(dist.glob("*"))
            if not dist_artifacts:
                self.record("packaging.twine", 1, "", "no artifacts in dist/")
                return self._finish(1)
            twine_argv = [py, "-m", "twine", "check", *[str(path) for path in dist_artifacts]]
            twine_rc, twine_out = self.run_step(twine_argv, cwd=self.root)
            self.record("packaging.twine", twine_rc, twine_out)
            if twine_rc != 0:
                return self._finish(twine_rc)

            version = _package_version(self.root)
            wheels = sorted(dist.glob(f"spell_sync-{version}-*.whl"))
            sdists = sorted(dist.glob(f"spell_sync-{version}.tar.gz"))
            if len(wheels) != 1 or len(sdists) != 1:
                detail = (
                    f"expected one wheel and one sdist for {version}, "
                    f"found wheels={len(wheels)} sdists={len(sdists)}"
                )
                self.record("packaging.wheel-smoke", 1, detail)
                return self._finish(1)

            smoke_root = Path(tempfile.mkdtemp(prefix="spell-sync-smoke."))
            self.cleanup_paths.append(smoke_root)
            smoke_home = smoke_root / "home"
            smoke_home.mkdir()
            smoke_project = smoke_root / "project"
            smoke_project.mkdir()
            smoke_env = os.environ.copy()
            smoke_env["HOME"] = str(smoke_home)

            venv_dir = smoke_root / "venv"
            venv_rc, venv_out = self.run_step([py, "-m", "venv", str(venv_dir)], cwd=self.root)
            if venv_rc != 0:
                self.record("packaging.wheel-smoke", venv_rc, venv_out)
                return self._finish(venv_rc)

            venv_py = venv_dir / "bin" / "python"
            if not venv_py.is_file():
                venv_py = venv_dir / "Scripts" / "python.exe"
            if not venv_py.is_file():
                self.record("packaging.wheel-smoke", 1, "venv python interpreter missing")
                return self._finish(1)

            smoke_rc = 0
            smoke_out_parts: list[str] = []
            for cmd in (
                [str(venv_py), "-m", "pip", "install", "-q", str(wheels[0])],
                [str(venv_py), "-m", "spell_sync", "version"],
                [str(venv_py), "-m", "spell_sync", "--help"],
            ):
                rc, out = self.run_step(cmd, cwd=self.root, env=smoke_env)
                smoke_out_parts.append(out)
                if rc != 0:
                    smoke_rc = rc
                    break
            self.record("packaging.wheel-smoke", smoke_rc, "\n".join(smoke_out_parts))
            if smoke_rc != 0:
                return self._finish(smoke_rc)

            wordlist = smoke_project / "wordlist.txt"
            init_rc, init_out = self.run_step(
                [py, "-m", "spell_sync", "init", "-C", str(wordlist)],
                cwd=smoke_project,
                env=smoke_env,
            )
            self.record("smoke.init", init_rc, init_out)
            if init_rc != 0:
                return self._finish(init_rc)

            lint_rc, lint_out = self.run_step(
                [py, "-m", "spell_sync", "lint", "--strict", "-C", str(wordlist)],
                cwd=smoke_project,
                env=smoke_env,
            )
            self.record("smoke.lint", lint_rc, lint_out)
            if lint_rc != 0:
                return self._finish(lint_rc)

            tui_rc, tui_out = self.run_step(
                [py, "-m", "pytest", "tests/test_gui_smoke.py", "-q"],
                cwd=self.root,
            )
            self.record("smoke.tui", tui_rc, tui_out)
            if tui_rc != 0:
                return self._finish(tui_rc)

            passed_prefixes = ("docs.", "tests.", "coverage.")
            for check in self.checks:
                check_id = str(check["id"])
                if check["status"] == "passed" and check_id.startswith(passed_prefixes):
                    print(f"{check_id}: passed")
            return self._finish(0)
        except BaseException as exc:
            return self._handle_internal_failure(exc)
        finally:
            self._cleanup()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run spell-sync CI checks with machine-readable summary output.",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Skip dependency installation (environment already prepared).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    python_bin = os.environ.get("PYTHON_BIN") or sys.executable
    runner = CiRunner(python_bin=python_bin)
    return runner.run(bootstrap=not args.no_bootstrap)


if __name__ == "__main__":
    raise SystemExit(main())
