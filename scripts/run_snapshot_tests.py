#!/usr/bin/env python3
"""Snapshot test gate with parent/child execution control."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.gate_flow import (  # noqa: E402
    gate_controller_for,
    open_gate_after_previews,
    preview_snapshot_child_plans,
    registry_for,
)
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.workspace_paths import (  # noqa: E402
    resolve_snapshot_workspace_layout,
    validate_snapshot_workspace,
)


def _run_child_with_plan(
    gate_controller,
    gate,
    step: str,
    command: list[str],
    child_plan,
    *,
    cwd: Path | None = None,
) -> int:
    rc, execution = gate_controller.run_child_with_plan(
        gate,
        child_plan,
        command=command,
        cwd=cwd or ROOT,
    )
    if execution is not None:
        print(f"SNAPSHOT_STEP={step} result={execution.timing.get('result', 'unknown')}")
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
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit archive output path for create/check steps",
    )
    args = parser.parse_args(argv)
    py = args.python

    valid, failed_id = validate_snapshot_workspace(args.workspace_root)
    if not valid:
        print("SNAPSHOT_GATE_RESULT=blocked")
        print(f"SNAPSHOT_GATE_FAILED_ID={failed_id}")
        return 1

    layout = resolve_snapshot_workspace_layout(args.workspace_root)
    assert layout is not None
    output_path = args.output if args.output is not None else layout.root / "snapshot" / "code.zip"
    dev_root = layout.spell_sync_dev
    pytest_test = dev_root / "tests" / "test_create_code_snapshot.py"
    snapshot_script = dev_root / "scripts" / "create-code-snapshot.py"
    workspace_flag = ["--workspace", str(layout.root)]
    output_flag = ["--output", str(output_path)]

    gate_controller = gate_controller_for(ROOT)
    registry = registry_for(ROOT)
    gate_command = [py, str(ROOT / "scripts" / "run_snapshot_tests.py")]
    preview_steps = (
        ("pytest", [py, "-m", "pytest", str(pytest_test), "-q"]),
        (
            "git",
            [
                py,
                "-c",
                (
                    "import subprocess, sys; "
                    "sys.exit(subprocess.call("
                    f"['git', 'status', '--porcelain'], cwd={str(layout.spell_sync)!r}))"
                ),
            ],
        ),
        ("archive-create", [py, str(snapshot_script), *workspace_flag, *output_flag, "--force"]),
        ("archive-check", [py, str(snapshot_script), *workspace_flag, *output_flag, "--check"]),
    )
    child_plans = preview_snapshot_child_plans(
        ROOT,
        registry,
        steps=preview_steps,
        workspace_root=layout.root,
        output_path=output_path,
    )
    gate, state, child_plans, _parent_plan = open_gate_after_previews(
        gate_controller,
        execution_id="gate:snapshot-tests",
        command=gate_command,
        mode="snapshot-tests",
        child_plans=child_plans,
        required=True,
    )
    if gate is None:
        return 0 if state == "reused" else 1

    exit_code = 0
    terminal_status: ExecutionStatus | None = None
    try:
        for (step, command), child_plan in zip(preview_steps, child_plans, strict=True):
            rc = _run_child_with_plan(
                gate_controller,
                gate,
                step,
                command,
                child_plan,
                cwd=dev_root if step == "pytest" else ROOT,
            )
            if rc != 0 or gate.stopped:
                exit_code = rc
                break
    except KeyboardInterrupt:
        exit_code = 130
        terminal_status = ExecutionStatus.INTERRUPTED
        raise
    finally:
        gate_controller.finish_gate(gate, exit_code=exit_code, status=terminal_status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
