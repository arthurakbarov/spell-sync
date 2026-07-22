#!/usr/bin/env python3
"""Snapshot test gate with parent/child execution control."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.mappings import snapshot_step_execution_id  # noqa: E402

SNAPSHOT_CHILD_IDS = (
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
    if gate.stopped:
        return rc
    if timing is not None:
        print(f"SNAPSHOT_STEP={step} result={timing.get('result', 'unknown')}")
    return rc


def _archive_path() -> Path:
    return ROOT / ".artifacts" / "snapshot" / "code-snapshot.tar.gz"


def _external_snapshot_script() -> Path | None:
    dev_root = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    if not dev_root:
        return None
    candidate = Path(dev_root) / "scripts" / "create-code-snapshot.py"
    return candidate if candidate.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run snapshot-tests gate.")
    parser.add_argument("--python", default=sys.executable)
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

    rc = _run_child(
        gate_controller,
        gate,
        "pytest",
        [py, "-m", "pytest", "tests/test_execution_registry.py", "-q"],
    )
    if rc != 0 or gate.stopped:
        gate_controller.finish_gate(gate, exit_code=rc)
        return rc

    git_cmd = [
        py,
        "-c",
        (
            "import subprocess, sys; "
            f"sys.exit(subprocess.call(['git', 'status', '--porcelain'], cwd={str(ROOT)!r}))"
        ),
    ]
    rc = _run_child(
        gate_controller,
        gate,
        "git",
        git_cmd,
    )
    if rc != 0 or gate.stopped:
        gate_controller.finish_gate(gate, exit_code=rc)
        return rc

    external = _external_snapshot_script()
    if external is not None:
        create_cmd = [py, str(external), "--force"]
        check_cmd = [py, str(external), "--check"]
    else:
        archive = _archive_path()
        archive.parent.mkdir(parents=True, exist_ok=True)
        create_cmd = [
            py,
            "-c",
            (
                "import tarfile, pathlib\n"
                f"root=pathlib.Path({str(ROOT)!r})\n"
                f"archive=pathlib.Path({str(archive)!r})\n"
                "archive.parent.mkdir(parents=True, exist_ok=True)\n"
                "with tarfile.open(archive, 'w:gz') as tar:\n"
                "    for rel in ('pyproject.toml', 'spell_sync', 'scripts', 'tests'):\n"
                "        path=root/rel\n"
                "        if path.exists():\n"
                "            tar.add(path, arcname=rel)\n"
                "print('SNAPSHOT_ARCHIVE=', archive)\n"
            ),
        ]
        check_cmd = [
            py,
            "-c",
            (
                "import pathlib, sys\n"
                f"archive=pathlib.Path({str(archive)!r})\n"
                "ok=archive.is_file() and archive.stat().st_size > 0\n"
                "print('archive-check=', 'ok' if ok else 'missing')\n"
                "sys.exit(0 if ok else 1)\n"
            ),
        ]

    rc = _run_child(gate_controller, gate, "archive-create", create_cmd)
    if rc != 0 or gate.stopped:
        gate_controller.finish_gate(gate, exit_code=rc)
        return rc

    rc = _run_child(gate_controller, gate, "archive-check", check_cmd)
    gate_controller.finish_gate(gate, exit_code=rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
