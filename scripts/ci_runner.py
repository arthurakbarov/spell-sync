#!/usr/bin/env python3
"""CI orchestrator: non-interactive checks, log retention, machine-readable summary.

``CiRunner`` is a single-use object: call ``run()`` once per instance.
"""

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "ci"
LOG_RETENTION = 5
SUMMARY_SCHEMA = 2
MIN_PYTHON = (3, 11)
INTERNAL_CHECK_ID = "ci.internal"

RunStep = Callable[..., tuple[int, str]]


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    run_id: str
    current_log: Path
    current_summary: Path
    history_log: Path
    history_summary: Path


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


def _run_id_from_log(path: Path) -> str | None:
    name = path.name
    if not name.startswith("ci-run-") or not name.endswith(".log"):
        return None
    return name[len("ci-run-") : -len(".log")]


def _run_id_from_summary(path: Path) -> str | None:
    name = path.name
    if not name.startswith("ci-summary-") or not name.endswith(".json"):
        return None
    return name[len("ci-summary-") : -len(".json")]


def _run_id_occupied(artifacts: Path, run_id: str) -> bool:
    return (artifacts / f"ci-run-{run_id}.log").exists() or (
        artifacts / f"ci-summary-{run_id}.json"
    ).exists()


def _completed_pairs(artifacts: Path) -> list[tuple[str, Path, Path]]:
    logs: dict[str, Path] = {}
    for path in artifacts.glob("ci-run-*.log"):
        run_id = _run_id_from_log(path)
        if run_id:
            logs[run_id] = path
    summaries: dict[str, Path] = {}
    for path in artifacts.glob("ci-summary-*.json"):
        run_id = _run_id_from_summary(path)
        if run_id:
            summaries[run_id] = path
    pairs = [(run_id, logs[run_id], summaries[run_id]) for run_id in logs if run_id in summaries]
    return sorted(pairs, key=lambda item: item[0], reverse=True)


def _rotate_completed_pairs(artifacts: Path, *, keep: int = LOG_RETENTION) -> None:
    for _run_id, log_path, summary_path in _completed_pairs(artifacts)[keep:]:
        log_path.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)


def _cleanup_orphan_artifacts(
    artifacts: Path,
    *,
    current_run_id: str,
    log_lines: list[str],
) -> None:
    log_ids = {
        run_id
        for path in artifacts.glob("ci-run-*.log")
        if (run_id := _run_id_from_log(path)) is not None
    }
    summary_ids = {
        run_id
        for path in artifacts.glob("ci-summary-*.json")
        if (run_id := _run_id_from_summary(path)) is not None
    }
    for run_id in (log_ids ^ summary_ids) - {current_run_id}:
        for name in (f"ci-run-{run_id}.log", f"ci-summary-{run_id}.json"):
            path = artifacts / name
            if path.exists():
                path.unlink(missing_ok=True)
                log_lines.append(f"warning: removed orphan artifact {name}")


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


def _wheel_smoke_env(base: dict[str, str], *, home: Path) -> dict[str, str]:
    env = {key: value for key, value in base.items() if key != "PYTHONPATH"}
    env["HOME"] = str(home)
    for key in list(env):
        if key.startswith("SPELL_SYNC") or key == "PYTHONSAFEPATH":
            del env[key]
    return env


def _verify_wheel_origin(origin: Path, *, venv_dir: Path, root: Path) -> tuple[bool, str]:
    origin_resolved = origin.resolve()
    venv_resolved = venv_dir.resolve()
    root_resolved = root.resolve()
    if root_resolved in origin_resolved.parents or origin_resolved == root_resolved:
        return False, f"import origin {origin_resolved} is inside checkout {root_resolved}"
    try:
        origin_resolved.relative_to(venv_resolved)
    except ValueError:
        return False, f"import origin {origin_resolved} is outside venv {venv_resolved}"
    return True, str(origin_resolved)


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
    while _run_id_occupied(artifacts, candidate):
        suffix += 1
        candidate = f"{base}-{suffix:02d}"
    return candidate


class CiRunner:
    """Single-use CI orchestrator. Create a new instance for each run."""

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
        self._run_artifacts: RunArtifacts | None = None
        self._used = False
        self._artifacts_ready = False
        self._wheel_smoke_root: Path | None = None

    def _bind_run_artifacts(self) -> RunArtifacts:
        run_id = _unique_run_id(self.artifacts, self.now())
        self.run_id = run_id
        artifacts = RunArtifacts(
            run_id=run_id,
            current_log=(self.artifacts / "ci.log").resolve(),
            current_summary=(self.artifacts / "ci-summary.json").resolve(),
            history_log=(self.artifacts / f"ci-run-{run_id}.log").resolve(),
            history_summary=(self.artifacts / f"ci-summary-{run_id}.json").resolve(),
        )
        self._run_artifacts = artifacts
        self._log_path = artifacts.current_log
        self._summary_path = artifacts.current_summary
        self._history_log_path = artifacts.history_log
        self._history_summary_path = artifacts.history_summary
        return artifacts

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

    def _print_emergency_failure(self) -> None:
        self._print_failure_block(
            1,
            summary_path="unavailable",
            log_path="unavailable",
            failed_checks=1,
            failed_id=INTERNAL_CHECK_ID,
        )

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
        _cleanup_orphan_artifacts(
            self.artifacts,
            current_run_id=self.run_id,
            log_lines=self.log_lines,
        )
        _rotate_completed_pairs(self.artifacts)
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
            self._print_emergency_failure()
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

    def _run_wheel_smoke(
        self,
        py: str,
        *,
        wheels: list[Path],
        version: str,
    ) -> tuple[int, str, str]:
        smoke_root = Path(tempfile.mkdtemp(prefix="spell-sync-smoke."))
        self.cleanup_paths.append(smoke_root)
        self._wheel_smoke_root = smoke_root
        smoke_home = smoke_root / "home"
        smoke_home.mkdir()
        outside_checkout = smoke_root / "outside-checkout"
        outside_checkout.mkdir()
        smoke_project = smoke_root / "project"
        smoke_project.mkdir()
        wheel_env = _wheel_smoke_env(os.environ, home=smoke_home)

        venv_dir = smoke_root / "venv"
        venv_rc, venv_out = self.run_step([py, "-m", "venv", str(venv_dir)], cwd=self.root)
        if venv_rc != 0:
            return venv_rc, venv_out, "venv creation failed"

        venv_py = venv_dir / "bin" / "python"
        if not venv_py.is_file():
            venv_py = venv_dir / "Scripts" / "python.exe"
        if not venv_py.is_file():
            return 1, "venv python interpreter missing", "venv python missing"

        parts: list[str] = []
        install_rc, install_out = self.run_step(
            [str(venv_py), "-m", "pip", "install", "-q", str(wheels[0])],
            cwd=outside_checkout,
            env=wheel_env,
        )
        parts.append(f"wheel install: exit={install_rc}")
        parts.append(install_out.rstrip())
        if install_rc != 0:
            return install_rc, "\n".join(parts), "wheel install failed"

        origin_script = """
import pathlib
import spell_sync
import importlib.metadata
origin = pathlib.Path(spell_sync.__file__).resolve()
print(origin)
print(importlib.metadata.version("spell-sync"))
"""
        origin_rc, origin_out = self.run_step(
            [str(venv_py), "-c", origin_script],
            cwd=outside_checkout,
            env=wheel_env,
        )
        parts.append(f"import origin probe: exit={origin_rc}")
        parts.append(origin_out.rstrip())
        if origin_rc != 0:
            return origin_rc, "\n".join(parts), "import origin probe failed"

        origin_lines = [line.strip() for line in origin_out.splitlines() if line.strip()]
        if len(origin_lines) < 2:
            return 1, "\n".join(parts), "import origin probe incomplete"
        origin_path = Path(origin_lines[0])
        metadata_version = origin_lines[1]
        ok, detail = _verify_wheel_origin(origin_path, venv_dir=venv_dir, root=self.root)
        parts.append(f"import origin: {detail}")
        if not ok:
            return 1, "\n".join(parts), detail
        parts.append(f"metadata version: {metadata_version}")
        if metadata_version != version:
            detail = f"metadata version {metadata_version!r} != pyproject {version!r}"
            parts.append(detail)
            return 1, "\n".join(parts), detail

        cli_commands = (
            [str(venv_py), "-m", "spell_sync", "version"],
            [str(venv_py), "-m", "spell_sync", "--help"],
            [str(venv_py), "-m", "spell_sync", "support-report", "--format", "json"],
        )
        for cmd in cli_commands:
            rc, out = self.run_step(cmd, cwd=outside_checkout, env=wheel_env)
            parts.append(f"cli {' '.join(cmd[2:])}: exit={rc}")
            parts.append(out.rstrip())
            if rc != 0:
                return rc, "\n".join(parts), f"cli failed: {' '.join(cmd[2:])}"

        summary = (
            f"wheel install ok; metadata {metadata_version}; "
            f"origin {detail}; cli version/help/support-report ok"
        )
        return 0, "\n".join(parts), summary

    def run(self, *, bootstrap: bool = True) -> int:
        if self._used:
            raise RuntimeError("CiRunner instances are single-use")
        self._used = True

        try:
            self.started_at = self.now().isoformat()
            py = self.python_bin
            self.artifacts.mkdir(parents=True, exist_ok=True)
            self._artifacts_ready = True
            self._bind_run_artifacts()
            minimum = _min_python_from_pyproject(self.root)

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

            smoke_rc, smoke_out, smoke_summary = self._run_wheel_smoke(
                py,
                wheels=wheels,
                version=version,
            )
            self.record("packaging.wheel-smoke", smoke_rc, smoke_out, smoke_summary)
            if smoke_rc != 0:
                return self._finish(smoke_rc)

            assert self._wheel_smoke_root is not None
            smoke_root = self._wheel_smoke_root
            smoke_home = smoke_root / "home"
            smoke_project = smoke_root / "project"
            smoke_env = _wheel_smoke_env(os.environ, home=smoke_home)

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
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            if self._artifacts_ready:
                return self._handle_internal_failure(exc)
            self._print_emergency_failure()
            return 1
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
