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

PLANNER_SCRIPT_FILES = (
    "scripts/build_focused_plan.py",
    "scripts/build_pre_final_plan.py",
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
    "environment.lock",
    "environment.check",
    "packaging.wheel-smoke",
    "tests.pytest",
    "gate:full-ci",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_gate_controller(text: str) -> list[str]:
    errors: list[str] = []
    if "GateController" not in text or (
        "begin_gate" not in text and "open_gate_after_previews" not in text
    ):
        errors.append(
            "[EXECUTION-CONTROL-GATE-001] scripts/ci_runner.py must use GateController gate; "
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
            "[EXECUTION-CONTROL-GATE-002] pip install steps must use bounded execution; "
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
        gate_markers = (
            "gate_controller_for",
            "open_gate_after_previews",
            "finish_gate",
        )
        if not all(marker in text for marker in gate_markers):
            errors.append(
                f"[EXECUTION-CONTROL-GATE-003] {rel} must use real GateController parent gate; "
                "remediation: wrap child steps in open_gate_after_previews/finish_gate"
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
    if "capture_ownership_snapshot" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-TERM-002] hard-timeout path must capture ownership before signals; "
            "remediation: add capture_ownership_snapshot in process_tree.py"
        )
    if "terminate_ownership_snapshot" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-TERM-002] termination must use captured ownership snapshot"
        )
    if "ProcessIdentity" not in process_tree or "start_marker" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-TERM-002] descendant cleanup must guard against PID reuse"
        )
    terminate = process_tree.split("def terminate_ownership_snapshot", 1)[-1].split("def ", 1)[0]
    if "collect_descendants(" in terminate:
        errors.append(
            "[EXECUTION-CONTROL-TERM-002] late-only descendant scan forbidden after signals"
        )
    if "_process_group_exists" not in process_tree:
        errors.append(
            "[EXECUTION-CONTROL-TERM-001] owned group existence must be checked before return"
        )
    return errors


def _check_parent_interrupt_runners() -> list[str]:
    errors: list[str] = []
    for rel in (
        "scripts/run_focused_tests.py",
        "scripts/run_pre_final_checks.py",
        "scripts/run_snapshot_tests.py",
        "scripts/ci_runner.py",
    ):
        text = _read(ROOT / rel)
        if "except KeyboardInterrupt" not in text:
            errors.append(
                f"[EXECUTION-CONTROL-INTERRUPT-003] {rel} must handle KeyboardInterrupt explicitly"
            )
        if "exit_code = 130" not in text or "ExecutionStatus.INTERRUPTED" not in text:
            errors.append(
                f"[EXECUTION-CONTROL-INTERRUPT-003] {rel} must set parent interrupted exit 130"
            )
        if "finally:" not in text or "finish_gate" not in text:
            errors.append(
                f"[EXECUTION-CONTROL-INTERRUPT-003] {rel} must finish gate exactly once in finally"
            )
    return errors


def _check_no_sync_diagnostic_fallback() -> list[str]:
    errors: list[str] = []
    diagnostics = _read(ROOT / "scripts/execution_control/diagnostics.py")
    if (
        "bundle_path.write_text" in diagnostics
        or "Path.write_text" in diagnostics.split("def collect_timeout_bundle", 1)[-1]
    ):
        if "bundle_path.write_text" in diagnostics:
            errors.append(
                "[EXECUTION-CONTROL-DIAGNOSTICS-003] sync bundle write after deadline forbidden"
            )
    if "_owned_process_snapshot" in diagnostics:
        errors.append(
            "[EXECUTION-CONTROL-DIAGNOSTICS-003] synchronous owned-process fallback forbidden"
        )
    if "DiagnosticBundleResult" not in diagnostics:
        errors.append(
            "[EXECUTION-CONTROL-DIAGNOSTICS-003] diagnostics must return incomplete bundle results"
        )
    return errors


def _check_aggregate_admission() -> list[str]:
    errors: list[str] = []
    for rel in (
        "scripts/execution_control/gate_admission.py",
        "scripts/execution_control/aggregate_plan.py",
        "scripts/execution_control/preview.py",
        "scripts/execution_control/gate_flow.py",
    ):
        if not (ROOT / rel).is_file():
            errors.append(f"[EXECUTION-CONTROL-ADMISSION-003] missing aggregate module {rel}")
    gate = _read(ROOT / "scripts/execution_control/gate_controller.py")
    if "prepare_gate_from_children" not in gate or "begin_gate_with_plan" not in gate:
        errors.append(
            "[EXECUTION-CONTROL-ADMISSION-003] gate controller must open gate after child previews"
        )
    focused = _read(ROOT / "scripts/run_focused_tests.py")
    if "open_gate_after_previews" not in focused or "run_bounded_planner" not in focused:
        errors.append(
            "[EXECUTION-CONTROL-ADMISSION-003] focused runner must plan before aggregate admission"
        )
    if focused.split("run_bounded_planner", 1)[0].count("begin_gate("):
        errors.append(
            "[EXECUTION-CONTROL-ADMISSION-003] focused runner must not begin_gate before planner"
        )
    return errors


def _check_parent_aggregate_timing() -> list[str]:
    errors: list[str] = []
    models = _read(ROOT / "scripts/execution_control/models.py")
    for field in (
        "planned_child_expected_sum",
        "planned_orchestration_overhead",
        "child_plan_digest",
    ):
        if field not in models:
            errors.append(f"[EXECUTION-CONTROL-AGGREGATE-001] ExecutionPlan missing {field}")
    ci = _read(ROOT / "scripts/ci_runner.py")
    if "plannedChildExpectedSum" not in ci and "preview_ci_child_plans" not in ci:
        errors.append(
            "[EXECUTION-CONTROL-AGGREGATE-001] full CI must preview child plans before gate"
        )
    return errors


def _check_snapshot_output_flag() -> list[str]:
    errors: list[str] = []
    runner = _read(ROOT / "scripts/run_snapshot_tests.py")
    if "--output" not in runner:
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-005] run_snapshot_tests.py must accept --output")
    if '"--output"' not in runner and "'--output'" not in runner:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-005] snapshot runner must pass --output to create script"
        )
    return errors


def _check_bootstrap_timeout() -> list[str]:
    errors: list[str] = []
    ci = _read(ROOT / "scripts/ci_runner.py")
    bootstrap_body = ci.split("def _run_bootstrap_python", 1)[-1].split("\n    def ", 1)[0]
    if "_run_bootstrap_python" not in ci or "BOOTSTRAP_PYTHON_HARD_SECONDS" not in bootstrap_body:
        errors.append(
            "[EXECUTION-CONTROL-BOOTSTRAP-001] bootstrap.python must use bounded subprocess timeout"
        )
    test_path = ROOT / "tests/test_execution_bootstrap_timeout.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-BOOTSTRAP-001] missing bootstrap timeout regression test")
    return errors


def _check_opaque_token_privacy() -> list[str]:
    errors: list[str] = []
    privacy = _read(ROOT / "scripts/execution_control/privacy.py")
    if "ADVERSARIAL_OPAQUE_TOKENS" not in privacy or "_ALL_LETTER_TOKEN_RE" not in privacy:
        errors.append(
            "[EXECUTION-CONTROL-PRIVACY-008] privacy must redact opaque all-letter/base64 tokens"
        )
    test_path = ROOT / "tests/test_execution_opaque_token_privacy.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-PRIVACY-008] missing opaque token privacy tests")
    return errors


def _check_round4_execution_tests() -> list[str]:
    errors: list[str] = []
    required = (
        "tests/test_execution_aggregate_plan.py",
        "tests/test_execution_real_admission.py",
        "tests/test_execution_diagnostic_no_fallback.py",
        "tests/test_execution_snapshot_output_isolation.py",
        "tests/test_execution_bootstrap_timeout.py",
        "tests/test_execution_process_fixture_cleanup.py",
        "tests/test_execution_opaque_token_privacy.py",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            errors.append(f"[EXECUTION-CONTROL-TESTS-002] missing Round 4 test file {rel}")
    return errors


def _check_planner_supervision() -> list[str]:
    errors: list[str] = []
    focused = _read(ROOT / "scripts/run_focused_tests.py")
    pre_final = _read(ROOT / "scripts/run_pre_final_checks.py")
    if "run_bounded_planner" not in focused or "build_focused_plan.py" not in focused:
        errors.append(
            "[EXECUTION-CONTROL-PLANNER-001] focused gate must run supervised planner child"
        )
    if "run_bounded_planner" not in pre_final or "build_pre_final_plan.py" not in pre_final:
        errors.append(
            "[EXECUTION-CONTROL-PLANNER-001] pre-final gate must run supervised planner child"
        )
    if "begin_gate(" in focused.split("run_bounded_planner", 1)[0]:
        errors.append(
            "[EXECUTION-CONTROL-PLANNER-001] focused planning before begin_gate forbidden"
        )
    if "open_gate_after_previews" not in focused:
        errors.append(
            "[EXECUTION-CONTROL-PLANNER-001] focused runner must aggregate previews before gate"
        )
    return errors


def _check_hermetic_snapshot_tests() -> list[str]:
    errors: list[str] = []
    path = ROOT / "tests/test_execution_snapshot_hermetic.py"
    if not path.is_file():
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-003] missing hermetic snapshot tests")
        return errors
    text = _read(path)
    if "snapshot.workspace-layout-invalid" not in text:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-003] hermetic tests must cover invalid workspace layout"
        )
    if "code.zip" not in text:
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-003] hermetic tests must guard owner code.zip")
    if "--workspace-root" not in text:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-003] hermetic tests must use explicit workspace root"
        )
    return errors


def _check_snapshot_workspace_root_flag() -> list[str]:
    errors: list[str] = []
    runner = _read(ROOT / "scripts/run_snapshot_tests.py")
    workspace_paths = _read(ROOT / "scripts/execution_control/workspace_paths.py")
    if "--workspace-root" not in runner:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-004] run_snapshot_tests.py must accept --workspace-root"
        )
    if "snapshot.workspace-layout-invalid" not in workspace_paths:
        errors.append(
            "[EXECUTION-CONTROL-SNAPSHOT-004] invalid layout must emit workspace-layout-invalid"
        )
    return errors


def _check_planner_scripts_exist() -> list[str]:
    errors: list[str] = []
    for rel in PLANNER_SCRIPT_FILES:
        if not (ROOT / rel).is_file():
            errors.append(f"[EXECUTION-CONTROL-PLANNER-002] missing planner script {rel}")
    return errors


def _check_profile_specificity(registry) -> list[str]:
    errors: list[str] = []
    pytest_mapping = registry.child_mappings.get("ci:pytest")
    docs_mapping = registry.child_mappings.get("ci:docs-style")
    if pytest_mapping is None or pytest_mapping.profile_id != "ci-pytest":
        errors.append("[EXECUTION-CONTROL-PROFILE-001] ci:pytest must map to ci-pytest profile")
    if docs_mapping is None or docs_mapping.profile_id != "ci-validator":
        errors.append(
            "[EXECUTION-CONTROL-PROFILE-001] docs validators must map to ci-validator profile"
        )
    pytest_profile = registry.profiles.get("ci-pytest")
    validator_profile = registry.profiles.get("ci-validator")
    child_profile = registry.profiles.get("ci-child")
    if (
        pytest_profile
        and validator_profile
        and pytest_profile.initial_hard_seconds <= validator_profile.initial_hard_seconds
    ):
        errors.append("[EXECUTION-CONTROL-PROFILE-001] pytest hard must exceed validator hard")
    if (
        child_profile
        and pytest_profile
        and child_profile.initial_hard_seconds >= pytest_profile.initial_hard_seconds
    ):
        errors.append(
            "[EXECUTION-CONTROL-PROFILE-001] generic ci-child must not inherit pytest hard budget"
        )
    if child_profile and child_profile.initial_hard_seconds > 300:
        errors.append("[EXECUTION-CONTROL-PROFILE-001] generic ci-child hard must remain 300")
    return errors


def _check_token_privacy_policy() -> list[str]:
    errors: list[str] = []
    privacy = _read(ROOT / "scripts/execution_control/privacy.py")
    if "_TOKEN_LIKE_RE" not in privacy or "_redact_token_like" not in privacy:
        errors.append(
            "[EXECUTION-CONTROL-PRIVACY-007] token-like regex policy must be applied in privacy.py"
        )
    token_test = ROOT / "tests/test_execution_token_privacy.py"
    if not token_test.is_file():
        errors.append("[EXECUTION-CONTROL-PRIVACY-007] missing token privacy tests")
    else:
        text = _read(token_test)
        if "secrets.token_urlsafe" not in text or "Bearer" not in text:
            errors.append(
                "[EXECUTION-CONTROL-PRIVACY-007] token privacy tests must use runtime secrets"
            )
    return errors


def _check_required_execution_tests() -> list[str]:
    errors: list[str] = []
    required = (
        "tests/test_execution_hard_timeout_detached.py",
        "tests/test_execution_parent_interrupt_status.py",
        "tests/test_execution_diagnostic_absolute_deadline.py",
        "tests/test_execution_snapshot_hermetic.py",
        "tests/test_execution_planner_supervision.py",
        "tests/test_execution_profile_specificity.py",
        "tests/test_execution_token_privacy.py",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            errors.append(f"[EXECUTION-CONTROL-TESTS-001] missing required test file {rel}")
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
    workspace_paths = _read(ROOT / "scripts/execution_control/workspace_paths.py")
    tokens = (
        "gate:snapshot-tests",
        "archive-create",
        "archive-check",
        "validate_snapshot_workspace",
        "SNAPSHOT_GATE_RESULT=blocked",
        "--workspace-root",
    )
    for token in tokens:
        if token not in text and token not in workspace_paths:
            errors.append(
                f"[EXECUTION-CONTROL-SNAPSHOT-001] snapshot gate must reference {token}; "
                "remediation: wire workspace-aware snapshot workflow"
            )
    if "snapshot-tests:pytest" not in text and "snapshot_step_execution_id" not in text:
        gate_flow = _read(ROOT / "scripts/execution_control/gate_flow.py")
        missing_pytest_map = (
            "snapshot-tests:pytest" not in gate_flow
            and "snapshot_step_execution_id" not in gate_flow
        )
        if missing_pytest_map:
            errors.append(
                "[EXECUTION-CONTROL-SNAPSHOT-001] snapshot gate must map pytest step execution id"
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


def _check_functional_output_separation() -> list[str]:
    errors: list[str] = []
    controller = _read(ROOT / "scripts/execution_control/controller.py")
    ci = _read(ROOT / "scripts/ci_runner.py")
    if "ControlledExecutionResult" not in controller:
        errors.append(
            "[EXECUTION-CONTROL-OUTPUT-001] controller must return ControlledExecutionResult"
        )
    if "raw_stdout_tail" not in controller:
        errors.append("[EXECUTION-CONTROL-OUTPUT-001] controller must retain raw stdout in-process")
    if (
        'timing.get("stdoutTail"'
        in ci.split("def _run_bounded_step", 1)[-1].split("def _run_check", 1)[0]
    ):
        errors.append(
            "[EXECUTION-CONTROL-OUTPUT-001] bounded steps must not parse sanitized stdoutTail"
        )
    test_path = ROOT / "tests/test_execution_wheel_origin_output.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-OUTPUT-001] missing wheel origin output separation tests")
    return errors


def _check_wheel_smoke_composite() -> list[str]:
    errors: list[str] = []
    ci = _read(ROOT / "scripts/ci_runner.py")
    mappings = _read(ROOT / "scripts/execution_control/mappings.py")
    toml = _read(ROOT / "tests/execution-budget.toml")
    required_ids = (
        "ci:wheel-smoke-venv",
        "ci:wheel-smoke-install",
        "ci:wheel-smoke-origin",
        "ci:wheel-smoke-version",
        "ci:wheel-smoke-cli-version",
        "ci:wheel-smoke-cli-help",
        "ci:wheel-smoke-support-report",
    )
    for execution_id in required_ids:
        if f'"{execution_id}"' not in toml:
            errors.append(f"[EXECUTION-CONTROL-WHEEL-001] missing child mapping {execution_id}")
        if execution_id not in mappings:
            errors.append(
                f"[EXECUTION-CONTROL-WHEEL-001] missing stable ID mapping for {execution_id}"
            )
    if "_wheel_smoke_composite_timing" not in ci:
        errors.append("[EXECUTION-CONTROL-WHEEL-001] wheel-smoke must emit composite timing")
    if "packaging.wheel-smoke.venv" not in ci:
        errors.append("[EXECUTION-CONTROL-WHEEL-001] wheel-smoke preview must list substeps")
    if "json.dumps(payload)" not in ci and "_WHEEL_ORIGIN_PROBE_SCRIPT" not in ci:
        errors.append("[EXECUTION-CONTROL-WHEEL-001] wheel origin must use structured JSON probe")
    if "PYTHONNOUSERSITE" not in ci:
        errors.append("[EXECUTION-CONTROL-WHEEL-002] wheel-smoke env must set PYTHONNOUSERSITE=1")
    return errors


def _check_workload_bootstrap_cost(registry) -> list[str]:
    errors: list[str] = []
    profile = registry.profiles.get("focused-pytest")
    if profile is None or profile.workload_cost is None:
        errors.append(
            "[EXECUTION-CONTROL-WORKLOAD-001] focused-pytest profile requires workloadCost"
        )
    prediction = _read(ROOT / "scripts/execution_control/prediction.py")
    if (
        "bootstrap-workload-cost" not in prediction
        or "WORKLOAD_SENSITIVE_EXECUTION_IDS" not in prediction
    ):
        errors.append(
            "[EXECUTION-CONTROL-WORKLOAD-001] prediction must apply bootstrap workload cost"
        )
    test_path = ROOT / "tests/test_execution_workload_prediction.py"
    if not test_path.is_file():
        errors.append("[EXECUTION-CONTROL-WORKLOAD-001] missing workload prediction tests")
    else:
        text = _read(test_path)
        if "edit_loop_budget_seconds=1" in text:
            errors.append(
                "[EXECUTION-CONTROL-WORKLOAD-002] admission proof must use normal committed budget"
            )
        if "test_normal_budget_large_focused_plan_narrows" not in text:
            errors.append("[EXECUTION-CONTROL-WORKLOAD-002] missing normal-budget admission proof")
    return errors


def _check_descendant_readiness_tests() -> list[str]:
    errors: list[str] = []
    path = ROOT / "tests/test_execution_descendant_cleanup.py"
    if not path.is_file():
        errors.append("[EXECUTION-CONTROL-PROCESS-001] missing descendant cleanup tests")
        return errors
    text = _read(path)
    if "hard_seconds=0.35" in text:
        errors.append(
            "[EXECUTION-CONTROL-PROCESS-001] descendant test must not use hard_seconds=0.35"
        )
    if "finally:" not in text:
        errors.append("[EXECUTION-CONTROL-PROCESS-001] descendant test must cleanup in finally")
    if "READY" not in text:
        errors.append("[EXECUTION-CONTROL-PROCESS-001] descendant test must use readiness protocol")
    return errors


def _check_non_vacuous_snapshot_tests() -> list[str]:
    errors: list[str] = []
    path = ROOT / "tests/test_execution_snapshot_hermetic.py"
    if not path.is_file():
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-006] missing hermetic snapshot tests")
        return errors
    text = _read(path)
    if "test_hermetic_snapshot_gate_parent_child_preview" not in text:
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-006] missing in-process hermetic snapshot test")
    if "code.zip" not in text:
        errors.append("[EXECUTION-CONTROL-SNAPSHOT-006] owner archive isolation proof required")
    return errors


def _check_ci_evidence_on_failure() -> list[str]:
    errors: list[str] = []
    evidence = _read(ROOT / "scripts/check-ci-evidence.py")
    if "CI_EVIDENCE_RESULT=success" not in evidence:
        errors.append("[EXECUTION-CONTROL-EVIDENCE-001] check-ci-evidence must emit success marker")
    ci = _read(ROOT / "scripts/ci_runner.py")
    if "_final_evidence" not in ci:
        errors.append("[EXECUTION-CONTROL-EVIDENCE-001] ci_runner must track final evidence mode")
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
                "gate_controller_for",
                "open_gate_after_previews",
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
    errors.extend(_check_parent_interrupt_runners())
    errors.extend(_check_no_sync_diagnostic_fallback())
    errors.extend(_check_aggregate_admission())
    errors.extend(_check_parent_aggregate_timing())
    errors.extend(_check_snapshot_output_flag())
    errors.extend(_check_bootstrap_timeout())
    errors.extend(_check_opaque_token_privacy())
    errors.extend(_check_round4_execution_tests())
    errors.extend(_check_hermetic_snapshot_tests())
    errors.extend(_check_snapshot_workspace_root_flag())
    errors.extend(_check_planner_supervision())
    errors.extend(_check_planner_scripts_exist())
    errors.extend(_check_profile_specificity(registry))
    errors.extend(_check_token_privacy_policy())
    errors.extend(_check_required_execution_tests())
    errors.extend(_check_interrupt_handshake())
    errors.extend(_check_dynamic_privacy_tests())
    errors.extend(_check_active_child_lease())
    errors.extend(_check_narrow_replacement_plan())
    errors.extend(_check_snapshot_integration())
    errors.extend(_check_atomic_ids(registry))
    errors.extend(_check_session_deltas())
    errors.extend(_check_functional_output_separation())
    errors.extend(_check_wheel_smoke_composite())
    errors.extend(_check_workload_bootstrap_cost(registry))
    errors.extend(_check_descendant_readiness_tests())
    errors.extend(_check_non_vacuous_snapshot_tests())
    errors.extend(_check_ci_evidence_on_failure())

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
