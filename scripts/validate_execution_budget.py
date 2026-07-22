#!/usr/bin/env python3
"""Validate execution budget registry and integration contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.identity import build_workload_payload  # noqa: E402
from scripts.execution_control.paths import history_database_path, state_root  # noqa: E402
from scripts.execution_control.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    load_registry,
    validate_registry,
)

MONITORED_FILES = (
    "scripts/ci_runner.py",
    "scripts/run_focused_tests.py",
    "scripts/run_pre_final_checks.py",
    "scripts/test_plan.py",
    "scripts/run_snapshot_tests.py",
)

FORBIDDEN_PATTERNS = (
    (re.compile(r"\|\s*tail\b"), "[EXECUTION-CONTROL-BOUNDARY-003] tail pipeline forbidden"),
    (re.compile(r"\|\s*tee\b"), "[EXECUTION-CONTROL-BOUNDARY-003] tee pipeline forbidden"),
)

ATOMIC_CI_IDS = (
    "ci:execution-budget-registry",
    "ci:ci-impact-registry",
    "ci:test-impact-registry",
    "ci:docs-style",
    "ci:docs-contract",
    "ci:agent-config",
    "ci:target-capabilities",
)

LONG_CI_STEP_MARKERS = (
    "deps.install",
    "deps.editable",
    "packaging.wheel-smoke",
    "tests.pytest",
    "gate:full-ci",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_gate_controller(text: str) -> list[str]:
    errors: list[str] = []
    if "GateController" not in text or "begin_gate" not in text:
        errors.append(
            "[EXECUTION-CONTROL-GATE-001] scripts/ci_runner.py must use GateController.begin_gate; "
            "remediation: integrate gate_controller for full-ci parent spans"
        )
    if "_finish_with_gate" not in text:
        errors.append(
            "[EXECUTION-CONTROL-GATE-001] scripts/ci_runner.py must finish parent gate via "
            "_finish_with_gate; remediation: record parent wall duration"
        )
    return errors


def _check_long_steps_bounded(text: str) -> list[str]:
    errors: list[str] = []
    pip_marker = (
        "self.run_step(\n"
        "                    [\n"
        '                        py,\n                        "-m",\n                        "pip"'
    )
    if pip_marker in text:
        errors.append(
            "[EXECUTION-CONTROL-GATE-002] deps.install must use bounded execution in full gate; "
            "remediation: route through _run_bounded_step"
        )
    wheel_section = text.split("def _run_wheel_smoke", 1)
    if len(wheel_section) > 1:
        body = wheel_section[1].split("def run", 1)[0]
        if "self.run_step(" in body:
            errors.append(
                "[EXECUTION-CONTROL-GATE-002] packaging.wheel-smoke internals must be bounded; "
                "remediation: use _run_bounded_step inside _run_wheel_smoke"
            )
    return errors


def _check_admission_narrow(text: str) -> list[str]:
    errors: list[str] = []
    controller = ROOT / "scripts/execution_control/controller.py"
    body = _read(controller)
    if "AdmissionDecision.NARROW" not in body or "BLOCKED_ADMISSION" not in body:
        errors.append(
            "[EXECUTION-CONTROL-ADMISSION-001] controller must block NARROW admission; "
            "remediation: return blocked-admission without subprocess in prepare_plan"
        )
    return errors


def _check_fingerprints() -> list[str]:
    errors: list[str] = []
    identity = _read(ROOT / "scripts/execution_control/identity.py")
    if "scriptBytesDigest" not in identity:
        errors.append(
            "[EXECUTION-CONTROL-FINGERPRINT-001] workload fingerprint must hash script bytes; "
            "remediation: extend build_workload_payload in identity.py"
        )
    if "moduleDigests" not in identity:
        errors.append(
            "[EXECUTION-CONTROL-FINGERPRINT-002] policy fingerprint must hash controller modules; "
            "remediation: extend policy_fingerprint in identity.py"
        )
    load_registry(ROOT / REGISTRY_REL_PATH)
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
    from scripts.execution_control.identity import workload_fingerprint

    if workload_fingerprint(execution_id="ci:pytest", workload=a) == workload_fingerprint(
        execution_id="ci:pytest", workload=b
    ):
        errors.append(
            "[EXECUTION-CONTROL-FINGERPRINT-001] different pytest targets must differ; "
            "remediation: include command targets in workload payload"
        )
    return errors


def _check_context_on_plan() -> list[str]:
    errors: list[str] = []
    models = _read(ROOT / "scripts/execution_control/models.py")
    controller = _read(ROOT / "scripts/execution_control/controller.py")
    if "context_signature" not in models:
        errors.append(
            "[EXECUTION-CONTROL-CONTEXT-001] ExecutionPlan must store context_signature; "
            "remediation: add field to models.ExecutionPlan"
        )
    if "build_context(execution_mode=plan.profile_id)" in controller:
        errors.append(
            "[EXECUTION-CONTROL-CONTEXT-001] controller must not rebuild context at span write; "
            "remediation: use plan.context_signature in insert_span"
        )
    return errors


def _check_progress_contracts() -> list[str]:
    errors: list[str] = []
    progress = _read(ROOT / "scripts/execution_control/progress.py")
    tail = progress.split("if line.strip():", 1)[-1][:80] if "if line.strip():" in progress else ""
    if "if line.strip():" in progress and "_mark_progress(now)" in tail:
        errors.append(
            "[EXECUTION-CONTROL-PROGRESS-001] generic arbitrary-output progress forbidden; "
            "remediation: remove catch-all mark_progress in progress.py"
        )
    return errors


def _check_interrupt_cleanup() -> list[str]:
    errors: list[str] = []
    process_tree = _read(ROOT / "scripts/execution_control/process_tree.py")
    if "except KeyboardInterrupt" not in process_tree or "finally:" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-INTERRUPT-001] process lifecycle must handle KeyboardInterrupt; "
            "remediation: wrap run_owned_command in try/finally"
        )
    controller = _read(ROOT / "scripts/execution_control/controller.py")
    if "_record_interrupt_span" not in controller:
        errors.append(
            "[EXECUTION-CONTROL-INTERRUPT-001] controller must record interrupted spans; "
            "remediation: add interrupt handling in controller.run"
        )
    return errors


def _check_diagnostics_deadline() -> list[str]:
    errors: list[str] = []
    diagnostics = _read(ROOT / "scripts/execution_control/diagnostics.py")
    if "_run_collector_process" not in diagnostics or "multiprocessing" not in diagnostics:
        errors.append(
            "[EXECUTION-CONTROL-DIAGNOSTICS-001] diagnostics must enforce per-collector deadline; "
            "remediation: use bounded subprocess collector in collect_timeout_bundle"
        )
    if "ThreadPoolExecutor" in diagnostics:
        errors.append(
            "[EXECUTION-CONTROL-DIAGNOSTICS-002] diagnostics must not wait on timed-out threads; "
            "remediation: remove ThreadPoolExecutor shutdown wait"
        )
    return errors


def _check_focused_pre_final_gates() -> list[str]:
    errors: list[str] = []
    for rel in ("scripts/run_focused_tests.py", "scripts/run_pre_final_checks.py"):
        text = _read(ROOT / rel)
        if "GateController" not in text or "begin_gate" not in text or "finish_gate" not in text:
            errors.append(
                f"[EXECUTION-CONTROL-GATE-003] {rel} must use real GateController parent gate; "
                "remediation: wrap child steps in begin_gate/finish_gate"
            )
        if "run_monitored_command" in text:
            errors.append(
                f"[EXECUTION-CONTROL-GATE-003] {rel} must not bypass parent gate "
                "via run_monitored_command"
            )
    return errors


def _check_parent_deadline_enforced() -> list[str]:
    errors: list[str] = []
    gate = _read(ROOT / "scripts/execution_control/gate_controller.py")
    process_tree = _read(ROOT / "scripts/execution_control/process_tree.py")
    controller = _read(ROOT / "scripts/execution_control/controller.py")
    if "parent_hard_deadline" not in gate or "parent_deadline_monotonic" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-DEADLINE-001] parent hard deadline must be enforced at runtime"
        )
    if "hard_seconds_override" not in controller:
        errors.append(
            "[EXECUTION-CONTROL-DEADLINE-001] controller must propagate parent remaining budget"
        )
    tests = ROOT / "tests/test_execution_parent_deadline.py"
    if not tests.is_file():
        errors.append("[EXECUTION-CONTROL-DEADLINE-001] missing parent deadline regression test")
    return errors


def _check_single_gate_finalization() -> list[str]:
    errors: list[str] = []
    gate = _read(ROOT / "scripts/execution_control/gate_controller.py")
    if "finish_gate" in gate.split("def run_child", 1)[1].split("def finish_gate", 1)[0]:
        errors.append("[EXECUTION-CONTROL-FINALIZE-001] run_child must not call finish_gate")
    if "finalized" not in gate or "terminal_timing" not in gate:
        errors.append("[EXECUTION-CONTROL-FINALIZE-001] gate must track finalized terminal state")
    return errors


def _check_soft_reporting_wired() -> list[str]:
    errors: list[str] = []
    process_tree = _read(ROOT / "scripts/execution_control/process_tree.py")
    if "print_soft_overrun" not in process_tree or "soft_report_plan" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-SOFT-001] soft-overrun reporter must be wired in execution loop"
        )
    return errors


def _check_process_group_cleanup() -> list[str]:
    errors: list[str] = []
    process_tree = _read(ROOT / "scripts/execution_control/process_tree.py")
    terminate = process_tree.split("def _terminate_owned_group", 1)[-1].split("def ", 1)[0]
    if "proc.poll()" in terminate and "return" in terminate:
        errors.append("[EXECUTION-CONTROL-TERM-001] leader exit must not skip group cleanup")
    if "_process_group_exists" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-TERM-001] owned group existence must be checked before return"
        )
    return errors


def _check_interrupt_handshake() -> list[str]:
    errors: list[str] = []
    test_path = ROOT / "tests/test_execution_parent_interrupt.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-INTERRUPT-002] missing interrupt readiness test")
        return errors
    text = _read(test_path)
    if "RUNNER_READY" not in text:
        errors.append("[EXECUTION-CONTROL-INTERRUPT-002] interrupt test must wait for RUNNER_READY")
    if "child_pid_file" not in text or "grandchild_pid_file" not in text:
        errors.append(
            "[EXECUTION-CONTROL-INTERRUPT-002] interrupt test must verify child/grandchild PIDs"
        )
    if "time.sleep(0.4)" in text:
        errors.append(
            "[EXECUTION-CONTROL-INTERRUPT-002] interrupt test must not guess timing with sleep"
        )
    return errors


def _check_dynamic_privacy_tests() -> list[str]:
    errors: list[str] = []
    test_path = ROOT / "tests/test_execution_dynamic_privacy.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-PRIVACY-006] missing dynamic privacy tests")
        return errors
    text = _read(test_path)
    if "Path.home()" not in text or "secrets." not in text:
        errors.append(
            "[EXECUTION-CONTROL-PRIVACY-006] privacy tests must use dynamic HOME/token values"
        )
    return errors


def _check_active_child_lease() -> list[str]:
    errors: list[str] = []
    history = _read(ROOT / "scripts/execution_control/history.py")
    gate = _read(ROOT / "scripts/execution_control/gate_controller.py")
    if "update_active_child" not in history:
        errors.append("[EXECUTION-CONTROL-LEASE-001] history must update active child on lease")
    if "update_active_child" not in gate:
        errors.append(
            "[EXECUTION-CONTROL-LEASE-001] gate controller must update active child lease"
        )
    return errors


def _check_narrow_replacement_plan() -> list[str]:
    errors: list[str] = []
    controller = _read(ROOT / "scripts/execution_control/controller.py")
    if "EXECUTION_REPLACEMENT_EXECUTION_ID" not in controller:
        errors.append(
            "[EXECUTION-CONTROL-ADMISSION-002] NARROW admission must emit replacement plan"
        )
    return errors


def _check_snapshot_integration() -> list[str]:
    errors: list[str] = []
    runner = ROOT / "scripts/run_snapshot_tests.py"
    if not runner.is_file():
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-001] missing scripts/run_snapshot_tests.py; "
            "remediation: add snapshot gate runner"
        )
        return errors
    text = _read(runner)
    tokens = (
        "gate:snapshot-tests",
        "snapshot-tests:pytest",
        "archive-create",
        "archive-check",
        "resolve_spell_sync_dev_root",
        "SNAPSHOT_GATE_RESULT=blocked",
    )
    for token in tokens:
        if token not in text:
            errors.append(
                f"[EXECUTION-CONTROL-SNAPSHOT-001] run_snapshot_tests.py must reference {token}; "
                "remediation: wire private snapshot workflow"
            )
    if "tarfile.open" in text:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-002] snapshot gate must not use fake tar fallback"
        )
    return errors


def _check_atomic_ids(registry) -> list[str]:
    errors: list[str] = []
    for execution_id in ATOMIC_CI_IDS:
        if execution_id not in registry.child_mappings:
            errors.append(
                f"[EXECUTION-CONTROL-IDS-001] missing child mapping for {execution_id}; "
                "remediation: add entry to tests/execution-budget.toml childMappings"
            )
    mappings = _read(ROOT / "scripts/execution_control/mappings.py")
    if '"ci:validators"' in mappings and "ci:execution-budget-registry" not in mappings:
        errors.append(
            "[EXECUTION-CONTROL-IDS-001] validators must not collapse to ci:validators; "
            "remediation: use atomic execution IDs in mappings.py"
        )
    return errors


def _check_session_deltas() -> list[str]:
    errors: list[str] = []
    session = _read(ROOT / "scripts/execution_control/session.py")
    if "lastUpdatedMonotonic" not in session or "now - started" in session:
        errors.append(
            "[EXECUTION-CONTROL-SESSION-001] session accounting must use delta updates; "
            "remediation: track lastUpdatedMonotonic in session.py"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    try:
        registry = load_registry(ROOT / REGISTRY_REL_PATH)
    except ValueError as exc:
        print(f"[EXECUTION-CONTROL-SCHEMA-001] {exc}")
        return 1
    errors.extend(validate_registry(registry))

    state = state_root()
    if str(state).startswith(str(ROOT.resolve())):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] state directory must be outside repository")

    db = history_database_path()
    if str(db).startswith(str(ROOT.resolve())):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] history database must be outside repository")

    gitignore = ROOT / ".gitignore"
    if not gitignore.is_file():
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] .gitignore must exist")
    elif ".artifacts/" not in gitignore.read_text(encoding="utf-8"):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] .artifacts/ must remain gitignore")

    for rel in MONITORED_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"[EXECUTION-CONTROL-BOUNDARY-003] missing monitored file {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if rel != "scripts/run_snapshot_tests.py":
            markers = (
                "run_monitored_command",
                "ExecutionController",
                "assess_admission",
                "GateController",
            )
            if not any(marker in text for marker in markers):
                errors.append(
                    f"[EXECUTION-CONTROL-BOUNDARY-003] {rel} must use execution controller"
                )
        for pattern, message in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                errors.append(message)

    ci_runner = ROOT / "scripts/ci_runner.py"
    if ci_runner.is_file():
        ci_text = _read(ci_runner)
        errors.extend(_check_gate_controller(ci_text))
        errors.extend(_check_long_steps_bounded(ci_text))

    errors.extend(_check_admission_narrow(_read(ROOT / "scripts/execution_control/admission.py")))
    errors.extend(_check_fingerprints())
    errors.extend(_check_context_on_plan())
    errors.extend(_check_progress_contracts())
    errors.extend(_check_interrupt_cleanup())
    errors.extend(_check_diagnostics_deadline())
    errors.extend(_check_focused_pre_final_gates())
    errors.extend(_check_parent_deadline_enforced())
    errors.extend(_check_single_gate_finalization())
    errors.extend(_check_soft_reporting_wired())
    errors.extend(_check_process_group_cleanup())
    errors.extend(_check_interrupt_handshake())
    errors.extend(_check_dynamic_privacy_tests())
    errors.extend(_check_active_child_lease())
    errors.extend(_check_narrow_replacement_plan())
    errors.extend(_check_snapshot_integration())
    errors.extend(_check_atomic_ids(registry))
    errors.extend(_check_session_deltas())

    product_paths = (
        "spell_sync/application/services/pull.py",
        "spell_sync/application/services/push.py",
        "spell_sync/application/services/recovery.py",
    )
    for rel in product_paths:
        path = ROOT / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "execution_control" in text or "run_monitored_command" in text:
                errors.append(
                    f"[EXECUTION-CONTROL-BOUNDARY-003] product path must not use controller: {rel}"
                )

    if errors:
        for item in errors:
            print(item)
        print(f"EXECUTION_BUDGET_VALIDATION=failed checks={len(errors)}")
        return 1
    print("EXECUTION_BUDGET_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
