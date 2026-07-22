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
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.workspace_paths import (  # noqa: E402
    resolve_snapshot_workspace_layout,
    validate_snapshot_workspace,
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
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Explicit workspace root containing spell-words/, spell-sync-dev/, and spell-sync/",
    )
    args = parser.parse_args(argv)
    py = args.python

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
    terminal_status: ExecutionStatus | None = None
    try:
        valid, failed_id = validate_snapshot_workspace(args.workspace_root)
        if not valid:
            print("SNAPSHOT_GATE_RESULT=blocked")
            print(f"SNAPSHOT_GATE_FAILED_ID={failed_id}")
            exit_code = 1
        else:
            layout = resolve_snapshot_workspace_layout(args.workspace_root)
            assert layout is not None
            dev_root = layout.spell_sync_dev
            pytest_test = dev_root / "tests" / "test_create_code_snapshot.py"
            snapshot_script = dev_root / "scripts" / "create-code-snapshot.py"
            workspace_flag = ["--workspace", str(layout.root)]
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
                        f"['git', 'status', '--porcelain'], cwd={str(layout.spell_sync)!r}))"
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
                        [py, str(snapshot_script), *workspace_flag, "--force"],
                        cwd=dev_root,
                    )
                    if rc != 0 or gate.stopped:
                        exit_code = rc
                    else:
                        rc = _run_child(
                            gate_controller,
                            gate,
                            "archive-check",
                            [py, str(snapshot_script), *workspace_flag, "--check"],
                            cwd=dev_root,
                        )
                        exit_code = rc
    except KeyboardInterrupt:
        exit_code = 130
        terminal_status = ExecutionStatus.INTERRUPTED
        raise
    finally:
        gate_controller.finish_gate(gate, exit_code=exit_code, status=terminal_status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
