"""Workload and policy fingerprint tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.identity import (  # noqa: E402
    POLICY_SOURCE_FILES,
    build_workload_payload,
    policy_fingerprint,
    workload_fingerprint,
)


def test_different_pytest_targets_have_different_fingerprints():
    a = build_workload_payload(
        root=ROOT,
        execution_id="ci:pytest",
        command=[sys.executable, "-m", "pytest", "tests/a.py"],
        mode="full-ci",
    )
    b = build_workload_payload(
        root=ROOT,
        execution_id="ci:pytest",
        command=[sys.executable, "-m", "pytest", "tests/b.py"],
        mode="full-ci",
    )
    assert workload_fingerprint(execution_id="ci:pytest", workload=a) != workload_fingerprint(
        execution_id="ci:pytest", workload=b
    )


def test_script_bytes_change_workload_fingerprint(tmp_path):
    script = tmp_path / "runner.py"
    script.write_text("print('v1')\n", encoding="utf-8")
    first = build_workload_payload(
        root=ROOT,
        execution_id="ci:pytest",
        command=[sys.executable, str(script)],
        mode="full-ci",
    )
    script.write_text("print('v2')\n", encoding="utf-8")
    second = build_workload_payload(
        root=ROOT,
        execution_id="ci:pytest",
        command=[sys.executable, str(script)],
        mode="full-ci",
    )
    assert workload_fingerprint(execution_id="ci:pytest", workload=first) != workload_fingerprint(
        execution_id="ci:pytest", workload=second
    )


def test_controller_bytes_change_policy_fingerprint(registry, monkeypatch):
    from scripts.execution_control import identity

    baseline = policy_fingerprint(registry, "full-ci")
    original_digest = identity._file_content_digest

    def _patched_digest(path):
        if path.name == "controller.py":
            return "changed-controller-bytes"
        return original_digest(path)

    monkeypatch.setattr(identity, "_file_content_digest", _patched_digest)
    changed = policy_fingerprint(registry, "full-ci")
    assert changed != baseline


def test_policy_modules_list_covers_controller_semantics():
    assert "controller.py" in POLICY_SOURCE_FILES
    assert "progress.py" in POLICY_SOURCE_FILES
    assert "process_tree.py" in POLICY_SOURCE_FILES
