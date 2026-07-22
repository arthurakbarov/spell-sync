#!/usr/bin/env python3
"""Snapshot test gate with parent/child execution control."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.mappings import snapshot_step_execution_id  # noqa: E402
from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root  # noqa: E402

SNAPSHOT_CHILD_EXECUTION_IDS = (
    "snapshot-tests:pytest",
    "snapshot-tests:git",
    "snapshot-tests:archive-create",
    "snapshot-tests:archive-check",
)


def _run_child(
    gate_controller: GateController,
    gate,
    step: str,
    command: list[str],
    *,
    cwd: Path | None = None,
) -> int:
    execution_id = snapshot_step_execution_id(step)
    rc, timing = gate_controller.run_child(
        gate,
        child_execution_id=execution_id,
        command=command,
        mode="snapshot-tests",
        required=True,
        cwd=cwd or ROOT,
    )
    if timing is not None:
        print(f"SNAPSHOT_STEP={step} result={timing.get('result', 'unknown')}")
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run snapshot-tests gate.")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    py = args.python
    dev_root = resolve_spell_sync_dev_root(ROOT)
    gate_controller = GateController.open_gate_controller(ROOT)
    gate, state = gate_controller.begin_gate(
        execution_id="gate:snapshot-tests",
        command=[py, str(ROOT / "scripts" / "run_snapshot_tests.py")],
        mode="snapshot-tests",
        required=True,
    )
    if gate is None:
        return 0 if state == "reused" else 1

    exit_code = 0
    try:
        if dev_root is None:
            print("SNAPSHOT_GATE_RESULT=blocked")
            print("SNAPSHOT_GATE_FAILED_ID=snapshot.private-root-unavailable")
            exit_code = 1
        else:
            pytest_test = dev_root / "tests" / "test_create_code_snapshot.py"
            snapshot_script = dev_root / "scripts" / "create-code-snapshot.py"
            rc = _run_child(
                gate_controller,
                gate,
                "pytest",
                [py, "-m", "pytest", str(pytest_test), "-q"],
                cwd=dev_root,
            )
            if rc != 0 or gate.stopped:
                exit_code = rc
            else:
                git_cmd = [
                    py,
                    "-c",
                    (
                        "import subprocess, sys; "
                        "sys.exit(subprocess.call("
                        f"['git', 'status', '--porcelain'], cwd={str(ROOT)!r}))"
                    ),
                ]
                rc = _run_child(gate_controller, gate, "git", git_cmd)
                if rc != 0 or gate.stopped:
                    exit_code = rc
                else:
                    rc = _run_child(
                        gate_controller,
                        gate,
                        "archive-create",
                        [py, str(snapshot_script), "--force"],
                        cwd=dev_root,
                    )
                    if rc != 0 or gate.stopped:
                        exit_code = rc
                    else:
                        rc = _run_child(
                            gate_controller,
                            gate,
                            "archive-check",
                            [py, str(snapshot_script), "--check"],
                            cwd=dev_root,
                        )
                        exit_code = rc
    finally:
        gate_controller.finish_gate(gate, exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
