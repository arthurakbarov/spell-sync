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
import time
import tomllib
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_history import summarize_ci_history  # noqa: E402
from scripts.ci_impact.registry import REGISTRY_REL_PATH, load_registry  # noqa: E402
from scripts.ci_input_state import compute_ci_input_state  # noqa: E402
from scripts.execution_control.controller import run_monitored_command  # noqa: E402
from scripts.execution_control.gate_controller import ActiveGate, GateController  # noqa: E402
from scripts.execution_control.gate_flow import (  # noqa: E402
    gate_controller_for,
    open_gate_after_previews,
    preview_ci_child_plans,
    registry_for,
)
from scripts.execution_control.mappings import ci_check_execution_id  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.test_selection.tree_state import (  # noqa: E402
    changed_source_paths,
    content_tree_digest,
    git_branch,
    git_detached,
    git_head,
)

ARTIFACTS = ROOT / ".artifacts" / "ci"
LOG_RETENTION = 5
SUMMARY_SCHEMA = 4
MIN_PYTHON = (3, 11)
INTERNAL_CHECK_ID = "ci.internal"

RunStep = Callable[..., tuple[int, str]]


def _ci_tree_digest(root: Path) -> str:
    return content_tree_digest(root)


def _full_ci_history_counts(artifacts: Path) -> dict[str, int]:
    counts = summarize_ci_history(artifacts)
    return counts.to_json_dict()


def _build_check_steps(py: str) -> list[tuple[str, list[str]]]:
    return [
        ("execution-budget.registry", [py, "scripts/validate_execution_budget.py"]),
        ("ci-impact.registry", [py, "scripts/validate_ci_impact.py"]),
        ("test-impact.registry", [py, "scripts/validate_test_impact.py"]),
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


def _check_ids(steps: list[tuple[str, list[str]]]) -> list[str]:
    return [step_id for step_id, _ in steps]


def _select_steps(
    steps: list[tuple[str, list[str]]],
    *,
    only: str | None,
    start_from: str | None,
    resume_failed: list[str] | None,
) -> list[tuple[str, list[str]]]:
    ids = _check_ids(steps)
    if resume_failed:
        selected = [item for item in steps if item[0] in resume_failed]
        if not selected:
            raise ValueError(f"resume-failed ids not found: {resume_failed}")
        return selected
    if only:
        selected = [item for item in steps if item[0] == only]
        if not selected:
            raise ValueError(f"unknown check id: {only}")
        return selected
    if start_from:
        if start_from not in ids:
            raise ValueError(f"unknown check id: {start_from}")
        index = ids.index(start_from)
        return steps[index:]
    return steps


BOOTSTRAP_PYTHON_HARD_SECONDS = 30.0


def _wheel_smoke_preview_steps(py: str) -> list[tuple[str, list[str], bool, bool, bool]]:
    return [
        ("packaging.wheel-smoke", [py, "-m", "venv", "placeholder"], False, False, True),
        (
            "packaging.wheel-smoke",
            [py, "-m", "pip", "install", "-q", "placeholder.whl"],
            False,
            False,
            True,
        ),
        (
            "packaging.wheel-smoke",
            [py, "-c", "import spell_sync; print('origin')"],
            False,
            False,
            True,
        ),
        ("packaging.wheel-smoke", [py, "-m", "spell_sync", "version"], False, False, True),
        ("packaging.wheel-smoke", [py, "-m", "spell_sync", "--help"], False, False, True),
        (
            "packaging.wheel-smoke",
            [py, "-m", "spell_sync", "support-report", "--format", "json"],
            False,
            False,
            True,
        ),
    ]


def _full_ci_preview_steps(py: str) -> tuple[tuple[str, list[str], bool, bool, bool], ...]:
    steps: list[tuple[str, list[str], bool, bool, bool]] = []
    for step_id, argv in _build_check_steps(py):
        coverage = step_id in {"tests.pytest", "coverage.policy"}
        steps.append((step_id, argv, coverage, False, False))
    steps.append(
        (
            "coverage.policy",
            _coverage_argv(py),
            True,
            False,
            False,
        )
    )
    steps.extend(
        [
            ("packaging.build", [py, "-m", "build"], False, False, False),
            (
                "packaging.twine",
                [py, "-m", "twine", "check", "placeholder.whl"],
                False,
                False,
                False,
            ),
        ]
    )
    steps.extend(_wheel_smoke_preview_steps(py))
    steps.extend(
        [
            (
                "smoke.init",
                [py, "-m", "spell_sync", "init", "-C", "wordlist.txt"],
                False,
                False,
                True,
            ),
            (
                "smoke.lint",
                [py, "-m", "spell_sync", "lint", "--strict", "-C", "wordlist.txt"],
                False,
                False,
                True,
            ),
            (
                "smoke.tui",
                [py, "-m", "pytest", "tests/test_gui_smoke.py", "-q"],
                False,
                True,
                False,
            ),
        ]
    )
    return tuple(steps)


def _ci_mode(*, only: str | None, start_from: str | None, resume_failed: bool) -> str:
    if resume_failed:
        return "resume"
    if only:
        return "only"
    if start_from:
        return "from"
    return "full"


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


def _coverage_argv(py: str) -> list[str]:
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
    return [py, "-c", script]


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
            self._uses_default_run_step = True
        else:
            self.run_step = run_step
            self._uses_default_run_step = False
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
        self._mode = "full"
        self._final_evidence = True
        self._tree_digest_before = ""
        self._tree_digest_after = ""
        self._ci_input_digest_before = ""
        self._ci_input_digest_after = ""
        self._parent_timing: dict[str, object] | None = None
        self._child_timeout_check_id = ""
        self._gate: ActiveGate | None = None
        self._gate_controller: GateController | None = None

    def _full_gate_active(self) -> bool:
        return self._mode == "full" and self._uses_default_run_step and self._gate is not None

    def _run_bootstrap_python(self, py: str) -> tuple[int, str, dict[str, object] | None]:
        started = time.monotonic()
        argv = [py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"]
        if not self._uses_default_run_step:
            rc, out = self.run_step(argv, cwd=self.root)
            elapsed = time.monotonic() - started
            timing = {
                "executionId": "bootstrap:python",
                "actualSeconds": round(elapsed, 2),
                "expectedSeconds": 5.0,
                "hardSeconds": BOOTSTRAP_PYTHON_HARD_SECONDS,
                "result": "success" if rc == 0 else "failed",
            }
            return rc, out, timing
        try:
            proc = subprocess.run(
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=BOOTSTRAP_PYTHON_HARD_SECONDS,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            timing: dict[str, object] = {
                "executionId": "bootstrap:python",
                "actualSeconds": round(elapsed, 2),
                "expectedSeconds": BOOTSTRAP_PYTHON_HARD_SECONDS,
                "hardSeconds": BOOTSTRAP_PYTHON_HARD_SECONDS,
                "result": "timeout-hard",
            }
            message = f"bootstrap.python timed out after {BOOTSTRAP_PYTHON_HARD_SECONDS:.0f}s"
            return 124, message, timing
        chunk = proc.stdout
        if proc.stderr:
            if chunk and not chunk.endswith("\n"):
                chunk += "\n"
            chunk += proc.stderr
        elapsed = time.monotonic() - started
        timing = {
            "executionId": "bootstrap:python",
            "actualSeconds": round(elapsed, 2),
            "expectedSeconds": 5.0,
            "hardSeconds": BOOTSTRAP_PYTHON_HARD_SECONDS,
            "result": "success" if proc.returncode == 0 else "failed",
        }
        return proc.returncode, chunk, timing

    def _begin_full_ci_gate(self, py: str) -> tuple[int, ActiveGate | None]:
        self._gate_controller = gate_controller_for(self.root)
        registry = registry_for(self.root)
        preview_steps = _full_ci_preview_steps(py)
        child_plans = preview_ci_child_plans(
            self.root,
            registry,
            steps=preview_steps,
            mode="full-ci",
        )
        gate, state, _child_plans, _parent_plan = open_gate_after_previews(
            self._gate_controller,
            execution_id="gate:full-ci",
            command=[py, str(self.root / "scripts" / "ci_runner.py")],
            mode="full-ci",
            child_plans=child_plans,
            required=True,
            coverage=True,
            packaging=True,
        )
        if gate is None:
            return 1 if state != "reused" else 0, None
        self._gate = gate
        return 0, gate

    def _run_bounded_step(
        self,
        step_id: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        coverage: bool = False,
        tui: bool = False,
        packaging: bool = False,
    ) -> tuple[int, str, dict[str, object] | None]:
        if (
            self._full_gate_active()
            and self._gate_controller is not None
            and self._gate is not None
        ):
            execution_id = ci_check_execution_id(step_id)
            rc, timing = self._gate_controller.run_child(
                self._gate,
                child_execution_id=execution_id,
                command=argv,
                mode="full-ci",
                required=True,
                cwd=cwd or self.root,
                env=env,
                coverage=coverage,
                tui=tui,
                packaging=packaging,
            )
            if timing is None:
                return rc, "", None
            result = str(timing.get("result", ""))
            out = str(timing.get("stdoutTail", "")) + str(timing.get("stderrTail", ""))
            if result in {"timeout-hard", "timeout-stall"}:
                self._child_timeout_check_id = step_id
                return 124, out or f"{step_id}: execution timeout ({result})", timing
            if self._gate.stopped:
                return rc, out, timing
            return rc, out, timing
        rc, out = self.run_step(argv, cwd=cwd or self.root, env=env)
        return rc, out, None

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

    def _finish(self, exit_code: int, *, failed_id: str = "") -> int:
        return self.finish(exit_code, failed_id=failed_id)

    def record(
        self,
        step_id: str,
        rc: int,
        output: str,
        summary: str = "",
        *,
        timing: dict[str, object] | None = None,
    ) -> None:
        entry: dict[str, object] = {
            "id": step_id,
            "status": "passed" if rc == 0 else "failed",
            "exitCode": rc,
        }
        if summary:
            entry["summary"] = summary
        if timing is not None:
            entry["timing"] = timing
        self.checks.append(entry)
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

    def _run_check(
        self,
        step_id: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, dict[str, object] | None]:
        coverage = step_id in {"tests.pytest", "coverage.policy"}
        tui = step_id == "smoke.tui"
        packaging = step_id.startswith("packaging.") or step_id.startswith("smoke.")
        if self._full_gate_active():
            return self._run_bounded_step(
                step_id,
                argv,
                cwd=cwd,
                env=env,
                coverage=coverage,
                tui=tui,
                packaging=packaging,
            )
        if self._mode != "full" or not self._uses_default_run_step:
            rc, out = self.run_step(argv, cwd=cwd or self.root, env=env)
            return rc, out, None
        execution_id = ci_check_execution_id(step_id)
        rc, timing = run_monitored_command(
            self.root,
            execution_id=execution_id,
            command=argv,
            mode="full-ci",
            required=True,
            cwd=cwd or self.root,
            env=env,
            coverage=coverage,
            tui=tui,
            packaging=packaging,
            enforce_hard=True,
            enforce_stall=False,
        )
        if timing is None:
            return 0, "", None
        result = str(timing.get("result", ""))
        out = str(timing.get("stdoutTail", "")) + str(timing.get("stderrTail", ""))
        if result in {"timeout-hard", "timeout-stall"}:
            self._child_timeout_check_id = step_id
            return 124, out or f"{step_id}: execution timeout ({result})", timing
        return rc, out, timing

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
        if self._child_timeout_check_id:
            print(f"CI_TIMEOUT_CHECK_ID={self._child_timeout_check_id}")
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

    def _build_parent_timing(self, exit_code: int) -> dict[str, object] | None:
        if self._parent_timing is not None:
            return self._parent_timing
        timings = [
            check["timing"] for check in self.checks if isinstance(check.get("timing"), dict)
        ]
        if not timings:
            return None
        child_expected = sum(float(item.get("expectedSeconds", 0)) for item in timings)
        overhead = max(10.0, child_expected * 0.1)
        parent_expected = child_expected + overhead
        soft = min(1800.0, max(parent_expected * 1.5, child_expected * 1.5))
        hard = min(1800.0, max(parent_expected * 1.5, soft + 10.0))
        actual = sum(float(item.get("actualSeconds", 0)) for item in timings)
        sample_count = max(int(item.get("sampleCount", 0)) for item in timings)
        confidence = next(
            (str(item.get("confidence", "none")) for item in timings if item.get("confidence")),
            "none",
        )
        source = next(
            (
                str(item.get("predictionSource", "registry-default"))
                for item in timings
                if item.get("predictionSource")
            ),
            "registry-default",
        )
        return {
            "executionId": "gate:full-ci",
            "profileId": "full-ci",
            "expectedSeconds": round(parent_expected),
            "plannedChildExpectedSum": round(child_expected, 2),
            "plannedOrchestrationOverhead": round(overhead, 2),
            "softSeconds": round(soft),
            "stallSeconds": None,
            "hardSeconds": round(hard),
            "actualSeconds": round(actual, 2),
            "predictionSource": source,
            "confidence": confidence,
            "sampleCount": sample_count,
            "result": "success" if exit_code == 0 else "failed",
        }

    def _finish_with_gate(self, exit_code: int, *, failed_id: str = "") -> int:
        if self._gate is not None and self._gate_controller is not None:
            self._parent_timing = self._gate_controller.finish_gate(self._gate, exit_code=exit_code)
            self._gate = None
        return self._finish(exit_code, failed_id=failed_id)

    def finish(self, exit_code: int, *, failed_id: str = "") -> int:
        failed = sum(1 for c in self.checks if c["status"] == "failed")
        computed_failed_id = failed_id or next(
            (str(c["id"]) for c in self.checks if c["status"] == "failed"),
            "",
        )
        if self._child_timeout_check_id and not failed_id:
            computed_failed_id = "execution.hard-timeout"
        failed_id = computed_failed_id
        if self._mode == "full":
            if self._parent_timing is None:
                self._parent_timing = self._build_parent_timing(exit_code)
        self._tree_digest_after = _ci_tree_digest(self.root)
        registry = load_registry(self.root / REGISTRY_REL_PATH)
        self._ci_input_digest_after = compute_ci_input_state(self.root, registry).digest
        tree_stable = self._tree_digest_before == self._tree_digest_after
        ci_input_stable = self._ci_input_digest_before == self._ci_input_digest_after
        if self._mode == "full" and not tree_stable and exit_code == 0:
            exit_code = 1
            failed = max(failed, 1)
            failed_id = "ci.tree-changed"
            self._final_evidence = False
            self.checks.append(
                {
                    "id": "ci.tree-changed",
                    "status": "failed",
                    "exitCode": 1,
                    "summary": "source/test/config tree changed during CI",
                }
            )
        if self._mode == "full" and not ci_input_stable and exit_code == 0:
            exit_code = 1
            failed = max(failed, 1)
            failed_id = "ci.ci-input-changed"
            self._final_evidence = False
            self.checks.append(
                {
                    "id": "ci.ci-input-changed",
                    "status": "failed",
                    "exitCode": 1,
                    "summary": "CI-relevant inputs changed during CI",
                }
            )
        completed = self.now().isoformat()
        run_head = git_head(self.root)
        payload = {
            "schemaVersion": SUMMARY_SCHEMA,
            "runId": self.run_id,
            "result": "success" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "startedAt": self.started_at,
            "completedAt": completed,
            "mode": self._mode,
            "finalEvidence": self._final_evidence,
            "gitHeadAtRun": run_head,
            "gitHead": run_head,
            "gitBranch": git_branch(self.root),
            "gitDetached": git_detached(self.root),
            "repositoryTreeDigest": self._tree_digest_after,
            "treeDigest": self._tree_digest_after,
            "treeDigestBefore": self._tree_digest_before,
            "treeDigestAfter": self._tree_digest_after,
            "treeStable": tree_stable,
            "ciInputDigest": self._ci_input_digest_after,
            "ciInputDigestBefore": self._ci_input_digest_before,
            "ciInputDigestAfter": self._ci_input_digest_after,
            "ciInputStable": ci_input_stable,
            "ciImpactSchemaVersion": registry.schema_version,
            "evidenceScope": "full-ci-inputs",
            "reusableAcrossNonCiCommits": True,
            "checks": self.checks,
            "logPath": str(self._log_path),
            "historyLogPath": str(self._history_log_path),
            "historySummaryPath": str(self._history_summary_path),
        }
        if failed_id:
            payload["failedCheckId"] = failed_id
        if self._child_timeout_check_id:
            payload["timeoutCheckId"] = self._child_timeout_check_id
        if self._parent_timing is not None:
            payload["timing"] = self._parent_timing
        text = "\n".join(self.log_lines) + "\n"
        _atomic_write(self._log_path, text)
        _atomic_write(self._history_log_path, text)
        if self._mode == "full":
            _atomic_write(
                self._history_summary_path,
                json.dumps(payload, indent=2) + "\n",
            )
        _cleanup_orphan_artifacts(
            self.artifacts,
            current_run_id=self.run_id,
            log_lines=self.log_lines,
        )
        _rotate_completed_pairs(self.artifacts)
        if self._mode == "full":
            history_dict = summarize_ci_history(self.artifacts).to_json_dict()
            payload["historyAtCompletion"] = history_dict
            payload["fullCiAttempts"] = history_dict["fullCiAttempts"]
            payload["fullCiFailures"] = history_dict["fullCiFailures"]
            payload["fullCiSuccesses"] = history_dict["fullCiSuccesses"]
        summary_text = json.dumps(payload, indent=2) + "\n"
        _atomic_write(self._summary_path, summary_text)
        if self._mode == "full":
            _atomic_write(self._history_summary_path, summary_text)
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
        venv_rc, venv_out, _ = self._run_bounded_step(
            "packaging.wheel-smoke",
            [py, "-m", "venv", str(venv_dir)],
            cwd=self.root,
        )
        if venv_rc != 0:
            return venv_rc, venv_out, "venv creation failed"

        venv_py = venv_dir / "bin" / "python"
        if not venv_py.is_file():
            venv_py = venv_dir / "Scripts" / "python.exe"
        if not venv_py.is_file():
            return 1, "venv python interpreter missing", "venv python missing"

        parts: list[str] = []
        install_rc, install_out, _ = self._run_bounded_step(
            "packaging.wheel-smoke",
            [str(venv_py), "-m", "pip", "install", "-q", str(wheels[0])],
            cwd=outside_checkout,
            env=wheel_env,
            packaging=True,
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
        origin_rc, origin_out, _ = self._run_bounded_step(
            "packaging.wheel-smoke",
            [str(venv_py), "-c", origin_script],
            cwd=outside_checkout,
            env=wheel_env,
            packaging=True,
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
            rc, out, _ = self._run_bounded_step(
                "packaging.wheel-smoke",
                cmd,
                cwd=outside_checkout,
                env=wheel_env,
                packaging=True,
            )
            parts.append(f"cli {' '.join(cmd[2:])}: exit={rc}")
            parts.append(out.rstrip())
            if rc != 0:
                return rc, "\n".join(parts), f"cli failed: {' '.join(cmd[2:])}"

        summary = (
            f"wheel install ok; metadata {metadata_version}; "
            f"origin {detail}; cli version/help/support-report ok"
        )
        return 0, "\n".join(parts), summary

    def run(
        self,
        *,
        bootstrap: bool = True,
        only: str | None = None,
        start_from: str | None = None,
        resume_failed: list[str] | None = None,
    ) -> int:
        if self._used:
            raise RuntimeError("CiRunner instances are single-use")
        self._used = True
        self._mode = _ci_mode(
            only=only,
            start_from=start_from,
            resume_failed=resume_failed is not None,
        )
        self._final_evidence = self._mode == "full"
        registry = load_registry(self.root / REGISTRY_REL_PATH)
        self._tree_digest_before = _ci_tree_digest(self.root)
        self._ci_input_digest_before = compute_ci_input_state(self.root, registry).digest

        exit_code = 0
        terminal_status: ExecutionStatus | None = None
        try:
            self.started_at = self.now().isoformat()
            py = self.python_bin
            self.artifacts.mkdir(parents=True, exist_ok=True)
            self._artifacts_ready = True
            self._bind_run_artifacts()
            minimum = _min_python_from_pyproject(self.root)

            pyver_rc, pyver_out, pyver_timing = self._run_bootstrap_python(py)
            pyver = pyver_out.strip().splitlines()[-1] if pyver_out.strip() else ""
            if pyver_rc != 0 or not _python_version_ok(pyver, minimum):
                detail = (
                    pyver_out.strip()
                    or f"unsupported Python {pyver!r} via {py} (need>={minimum[0]}.{minimum[1]})"
                )
                self.record("bootstrap.python", 1, detail, timing=pyver_timing)
                return self._finish_with_gate(1)
            self.record("bootstrap.python", 0, f"python {pyver} via {py}", timing=pyver_timing)

            gate_rc = 0
            if self._mode == "full" and self._uses_default_run_step:
                gate_rc, gate = self._begin_full_ci_gate(py)
                if gate_rc != 0:
                    return self._finish_with_gate(gate_rc)
                if gate is None:
                    return self._finish_with_gate(0)

            dirty_paths = changed_source_paths(self.root)
            if dirty_paths and self._mode == "full":
                preview = ", ".join(dirty_paths[:8])
                if len(dirty_paths) > 8:
                    preview += f" (+{len(dirty_paths) - 8} more)"
                self.record(
                    "bootstrap.clean-tree",
                    1,
                    f"dirty source tree: {preview}",
                )
                self._final_evidence = False
                return self._finish_with_gate(1)
            if dirty_paths:
                self._final_evidence = False
            elif self._mode == "full":
                _, clean_out, clean_timing = self._run_bounded_step(
                    "bootstrap.clean-tree",
                    [py, "-c", "print('clean')"],
                    cwd=self.root,
                )
                self.record(
                    "bootstrap.clean-tree",
                    0,
                    clean_out or "working tree clean",
                    timing=clean_timing,
                )

            if bootstrap:
                install_rc, install_out, install_timing = self._run_bounded_step(
                    "deps.install",
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
                self.record("deps.install", install_rc, install_out, timing=install_timing)
                if install_rc != 0:
                    return self._finish_with_gate(install_rc)

                install_editable_rc, install_editable_out, editable_timing = self._run_bounded_step(
                    "deps.editable",
                    [py, "-m", "pip", "install", "-q", "-e", "."],
                    cwd=self.root,
                )
                self.record(
                    "deps.editable",
                    install_editable_rc,
                    install_editable_out,
                    timing=editable_timing,
                )
                if install_editable_rc != 0:
                    return self._finish_with_gate(install_editable_rc)

            steps = _build_check_steps(py)
            try:
                selected = _select_steps(
                    steps,
                    only=only,
                    start_from=start_from,
                    resume_failed=resume_failed,
                )
            except ValueError as exc:
                self.record(INTERNAL_CHECK_ID, 1, str(exc))
                return self._finish_with_gate(1)

            run_post_pytest = self._mode == "full" or start_from == "tests.pytest"
            if resume_failed:
                run_post_pytest = run_post_pytest or any(
                    item in {"tests.pytest", "coverage.policy"} for item in resume_failed
                )

            for step_id, argv in selected:
                rc, out, timing = self._run_check(step_id, argv, cwd=self.root)
                summary = self._fail_summary(step_id, out) if rc != 0 else ""
                self.record(step_id, rc, out, summary, timing=timing)
                if rc != 0:
                    if self._child_timeout_check_id:
                        return self._finish_with_gate(rc, failed_id="execution.hard-timeout")
                    return self._finish_with_gate(rc)

            if not run_post_pytest:
                return self._finish_with_gate(0)

            if only is None and (self._mode == "full" or start_from == "tests.pytest"):
                cov_rc, cov_out, cov_timing = self._run_check(
                    "coverage.policy",
                    _coverage_argv(py),
                    cwd=self.root,
                )
                self.record("coverage.policy", cov_rc, cov_out, timing=cov_timing)
                if cov_rc != 0:
                    if self._child_timeout_check_id:
                        return self._finish_with_gate(cov_rc, failed_id="execution.hard-timeout")
                    return self._finish_with_gate(cov_rc)

            if self._mode != "full" and only not in {None, "tests.pytest"}:
                return self._finish_with_gate(0)

            shutil.rmtree(self.root / "build", ignore_errors=True)
            shutil.rmtree(self.root / "dist", ignore_errors=True)
            shutil.rmtree(self.root / "spell_sync.egg-info", ignore_errors=True)
            build_rc, build_out, build_timing = self._run_check(
                "packaging.build",
                [py, "-m", "build"],
                cwd=self.root,
            )
            self.record("packaging.build", build_rc, build_out, timing=build_timing)
            if build_rc != 0:
                return self._finish_with_gate(build_rc)

            dist = self.root / "dist"
            dist_artifacts = sorted(dist.glob("*"))
            if not dist_artifacts:
                self.record("packaging.twine", 1, "", "no artifacts in dist/")
                return self._finish_with_gate(1)
            twine_argv = [py, "-m", "twine", "check", *[str(path) for path in dist_artifacts]]
            twine_rc, twine_out, twine_timing = self._run_check(
                "packaging.twine",
                twine_argv,
                cwd=self.root,
            )
            self.record("packaging.twine", twine_rc, twine_out, timing=twine_timing)
            if twine_rc != 0:
                return self._finish_with_gate(twine_rc)

            version = _package_version(self.root)
            wheels = sorted(dist.glob(f"spell_sync-{version}-*.whl"))
            sdists = sorted(dist.glob(f"spell_sync-{version}.tar.gz"))
            if len(wheels) != 1 or len(sdists) != 1:
                detail = (
                    f"expected one wheel and one sdist for {version}, "
                    f"found wheels={len(wheels)} sdists={len(sdists)}"
                )
                self.record("packaging.wheel-smoke", 1, detail)
                return self._finish_with_gate(1)

            smoke_rc, smoke_out, smoke_summary = self._run_wheel_smoke(
                py,
                wheels=wheels,
                version=version,
            )
            self.record("packaging.wheel-smoke", smoke_rc, smoke_out, smoke_summary)
            if smoke_rc != 0:
                return self._finish_with_gate(smoke_rc)

            assert self._wheel_smoke_root is not None
            smoke_root = self._wheel_smoke_root
            smoke_home = smoke_root / "home"
            smoke_project = smoke_root / "project"
            smoke_env = _wheel_smoke_env(os.environ, home=smoke_home)

            wordlist = smoke_project / "wordlist.txt"
            init_rc, init_out, init_timing = self._run_check(
                "smoke.init",
                [py, "-m", "spell_sync", "init", "-C", str(wordlist)],
                cwd=smoke_project,
                env=smoke_env,
            )
            self.record("smoke.init", init_rc, init_out, timing=init_timing)
            if init_rc != 0:
                return self._finish_with_gate(init_rc)

            lint_rc, lint_out, lint_timing = self._run_check(
                "smoke.lint",
                [py, "-m", "spell_sync", "lint", "--strict", "-C", str(wordlist)],
                cwd=smoke_project,
                env=smoke_env,
            )
            self.record("smoke.lint", lint_rc, lint_out, timing=lint_timing)
            if lint_rc != 0:
                return self._finish_with_gate(lint_rc)

            tui_rc, tui_out, tui_timing = self._run_check(
                "smoke.tui",
                [py, "-m", "pytest", "tests/test_gui_smoke.py", "-q"],
                cwd=self.root,
            )
            self.record("smoke.tui", tui_rc, tui_out, timing=tui_timing)
            if tui_rc != 0:
                return self._finish_with_gate(tui_rc)

            passed_prefixes = ("docs.", "tests.", "coverage.")
            for check in self.checks:
                check_id = str(check["id"])
                if check["status"] == "passed" and check_id.startswith(passed_prefixes):
                    print(f"{check_id}: passed")
            return self._finish_with_gate(0)
        except KeyboardInterrupt:
            exit_code = 130
            terminal_status = ExecutionStatus.INTERRUPTED
            raise
        except BaseException as exc:
            if self._artifacts_ready:
                return self._handle_internal_failure(exc)
            self._print_emergency_failure()
            return 1
        finally:
            if (
                self._gate is not None
                and self._gate_controller is not None
                and not self._gate.finalized
            ):
                self._parent_timing = self._gate_controller.finish_gate(
                    self._gate,
                    exit_code=exit_code,
                    status=terminal_status,
                )
                self._gate = None
            self._cleanup()


def _load_resume_failed_ids(summary_path: Path, root: Path) -> tuple[list[str], str]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("resume summary must be a JSON object")
    summary_digest = payload.get("treeDigest")
    if not isinstance(summary_digest, str) or not summary_digest:
        raise ValueError("resume summary missing treeDigest")
    current_digest = _ci_tree_digest(root)
    if summary_digest != current_digest:
        raise ValueError("resume summary treeDigest does not match current tree")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise ValueError("resume summary missing checks")
    failed = [str(item["id"]) for item in checks if item.get("status") == "failed"]
    if not failed:
        raise ValueError("resume summary has no failed checks")
    return failed, current_digest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run spell-sync CI checks with machine-readable summary output.",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Skip dependency installation (environment already prepared).",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="Print stable check ids and exit.",
    )
    parser.add_argument(
        "--only",
        metavar="CHECK_ID",
        help="Run a single diagnostic check (not final CI evidence).",
    )
    parser.add_argument(
        "--from",
        dest="start_from",
        metavar="CHECK_ID",
        help="Run from CHECK_ID through remaining checks (diagnostic).",
    )
    parser.add_argument(
        "--resume-failed",
        metavar="SUMMARY_PATH",
        help="Rerun failed checks from a prior summary for the same tree digest.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    python_bin = os.environ.get("PYTHON_BIN") or sys.executable
    if args.list_checks:
        ids = _check_ids(_build_check_steps(python_bin))
        ids.extend(
            [
                "coverage.policy",
                "packaging.build",
                "packaging.twine",
                "packaging.wheel-smoke",
                "smoke.init",
                "smoke.lint",
                "smoke.tui",
            ]
        )
        for check_id in ids:
            print(check_id)
        return 0
    resume_failed: list[str] | None = None
    if args.resume_failed:
        summary_path = Path(args.resume_failed)
        if not summary_path.is_file():
            print(f"resume summary not found: {summary_path}", file=sys.stderr)
            return 1
        try:
            resume_failed, _digest = _load_resume_failed_ids(summary_path, ROOT)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.only and args.start_from:
        print("cannot combine --only and --from", file=sys.stderr)
        return 1
    runner = CiRunner(python_bin=python_bin)
    return runner.run(
        bootstrap=not args.no_bootstrap,
        only=args.only,
        start_from=args.start_from,
        resume_failed=resume_failed,
    )


if __name__ == "__main__":
    raise SystemExit(main())
