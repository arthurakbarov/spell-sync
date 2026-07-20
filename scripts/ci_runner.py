#!/usr/bin/env python3
"""CI orchestrator: non-interactive checks, log retention, machine-readable summary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "ci"
LOG_RETENTION = 5
SUMMARY_SCHEMA = 1
SUPPORTED_PYTHON = frozenset({"3.11", "3.12", "3.13"})

RunStep = Callable[..., tuple[int, str]]


def _python() -> str:
    for candidate in ("python3.11", "python3.12", "python3.13", "python3"):
        if shutil.which(candidate):
            return candidate
    return sys.executable


def _run_step(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        cwd=cwd or ROOT,
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
    _rotate_timestamped(artifacts, "ci-*.log", keep=LOG_RETENTION)
    _rotate_timestamped(artifacts, "ci-summary-*.json", keep=LOG_RETENTION)


def _package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise RuntimeError("pyproject.toml missing project.version")
    return version


def _coverage_gate(py: str, *, run_step: RunStep = _run_step) -> tuple[int, str]:
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
    return run_step([py, "-c", script])


class CiRunner:
    def __init__(
        self,
        *,
        root: Path = ROOT,
        artifacts: Path = ARTIFACTS,
        run_step: RunStep | None = None,
        now: Callable[[], datetime] | None = None,
        python_bin: str | None = None,
    ) -> None:
        self.root = root
        self.artifacts = artifacts
        self.run_step = run_step or _run_step
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.python_bin = python_bin
        self.checks: list[dict[str, object]] = []
        self.log_lines: list[str] = []
        self.cleanup_paths: list[Path] = []
        self.started_at = ""
        self._log_path = Path()
        self._summary_path = Path()
        self._stamp_log = Path()
        self._stamp_summary = Path()

    def _bind_artifact_paths(self, stamp: str) -> None:
        self._log_path = (self.artifacts / "ci.log").resolve()
        self._stamp_log = (self.artifacts / f"ci-{stamp}.log").resolve()
        self._summary_path = (self.artifacts / "ci-summary.json").resolve()
        self._stamp_summary = (self.artifacts / f"ci-summary-{stamp}.json").resolve()

    def _finish(self, exit_code: int) -> int:
        return self.finish(
            exit_code,
            log_path=self._log_path,
            summary_path=self._summary_path,
            stamp_log=self._stamp_log,
            stamp_summary=self._stamp_summary,
        )

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

    def finish(
        self,
        exit_code: int,
        *,
        log_path: Path,
        summary_path: Path,
        stamp_log: Path,
        stamp_summary: Path,
    ) -> int:
        failed = sum(1 for c in self.checks if c["status"] == "failed")
        failed_id = next((str(c["id"]) for c in self.checks if c["status"] == "failed"), "")
        completed = self.now().isoformat()
        payload = {
            "schemaVersion": SUMMARY_SCHEMA,
            "result": "success" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "startedAt": self.started_at,
            "completedAt": completed,
            "checks": self.checks,
            "logPath": str(log_path),
        }
        if failed_id:
            payload["failedCheckId"] = failed_id
        text = "\n".join(self.log_lines) + "\n"
        _atomic_write(log_path, text)
        _atomic_write(stamp_log, text)
        summary_text = json.dumps(payload, indent=2) + "\n"
        _atomic_write(summary_path, summary_text)
        _atomic_write(stamp_summary, summary_text)
        _rotate_logs(self.artifacts)
        print(f"CI_RESULT={'success' if exit_code == 0 else 'failed'}")
        print(f"CI_EXIT={exit_code}")
        if failed:
            print(f"CI_FAILED_CHECKS={failed}")
        if failed_id:
            print(f"CI_FAILED_ID={failed_id}")
        print(f"CI_SUMMARY={summary_path}")
        print(f"CI_LOG={log_path}")
        return exit_code

    def _cleanup(self) -> None:
        (self.root / "coverage.json").unlink(missing_ok=True)
        for path in self.cleanup_paths:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        shutil.rmtree(self.root / "build", ignore_errors=True)
        shutil.rmtree(self.root / "dist", ignore_errors=True)
        shutil.rmtree(self.root / "spell_sync.egg-info", ignore_errors=True)

    def run(self, *, bootstrap: bool = True) -> int:
        self.started_at = self.now().isoformat()
        py = self.python_bin or _python()
        self.artifacts.mkdir(parents=True, exist_ok=True)
        stamp = self.now().strftime("%Y%m%dT%H%M%SZ")
        self._bind_artifact_paths(stamp)

        try:
            pyver_rc, pyver_out = self.run_step(
                [py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            )
            pyver = pyver_out.strip().splitlines()[-1] if pyver_out.strip() else ""
            if pyver_rc != 0 or pyver not in SUPPORTED_PYTHON:
                detail = pyver_out.strip() or f"unsupported Python {pyver!r} via {py}"
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
                )
                self.record("deps.install", install_rc, install_out)
                if install_rc != 0:
                    return self._finish(install_rc)

                install_editable_rc, install_editable_out = self.run_step(
                    [py, "-m", "pip", "install", "-q", "-e", "."],
                )
                self.record("deps.editable", install_editable_rc, install_editable_out)
                if install_editable_rc != 0:
                    return self._finish(install_editable_rc)

            steps: list[tuple[str, list[str]]] = [
                ("docs.style", ["bash", "scripts/check-docs-style.sh"]),
                ("docs.contract", [py, "scripts/check-docs-contract.py"]),
                ("agent.config", [py, "scripts/check-agent-config.py"]),
                ("targets.capabilities", [py, "scripts/check-target-capabilities.py", "--check"]),
                ("ruff.check", [py, "-m", "ruff", "check", "spell_sync", "tests"]),
                ("ruff.format", [py, "-m", "ruff", "format", "--check", "spell_sync", "tests"]),
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
                rc, out = self.run_step(argv)
                summary = self._fail_summary(step_id, out) if rc != 0 else ""
                self.record(step_id, rc, out, summary)
                if rc != 0:
                    return self._finish(rc)

            cov_rc, cov_out = _coverage_gate(py, run_step=self.run_step)
            self.record("coverage.policy", cov_rc, cov_out)
            if cov_rc != 0:
                return self._finish(cov_rc)

            shutil.rmtree(self.root / "build", ignore_errors=True)
            shutil.rmtree(self.root / "dist", ignore_errors=True)
            shutil.rmtree(self.root / "spell_sync.egg-info", ignore_errors=True)
            build_rc, build_out = self.run_step([py, "-m", "build"])
            self.record("packaging.build", build_rc, build_out)
            if build_rc != 0:
                return self._finish(build_rc)

            dist = self.root / "dist"
            artifacts = sorted(dist.glob("*"))
            if not artifacts:
                self.record("packaging.twine", 1, "", "no artifacts in dist/")
                return self._finish(1)
            twine_argv = [py, "-m", "twine", "check", *[str(path) for path in artifacts]]
            twine_rc, twine_out = self.run_step(twine_argv)
            self.record("packaging.twine", twine_rc, twine_out)
            if twine_rc != 0:
                return self._finish(twine_rc)

            version = _package_version()
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
            venv_rc, venv_out = self.run_step([py, "-m", "venv", str(venv_dir)])
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
                rc, out = self.run_step(cmd, env=smoke_env)
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

            tui_rc, tui_out = self.run_step([py, "-m", "pytest", "tests/test_gui_smoke.py", "-q"])
            self.record("smoke.tui", tui_rc, tui_out)
            if tui_rc != 0:
                return self._finish(tui_rc)

            passed_prefixes = ("docs.", "tests.", "coverage.")
            for check in self.checks:
                check_id = str(check["id"])
                if check["status"] == "passed" and check_id.startswith(passed_prefixes):
                    print(f"{check_id}: passed")
            return self._finish(0)
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
    runner = CiRunner()
    return runner.run(bootstrap=not args.no_bootstrap)


if __name__ == "__main__":
    raise SystemExit(main())
