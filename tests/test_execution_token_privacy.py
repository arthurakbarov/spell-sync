"""Token and secret privacy across execution artifacts."""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.diagnostics import collect_timeout_bundle  # noqa: E402
from scripts.execution_control.models import ExecutionPlan, SpanRecord  # noqa: E402
from scripts.execution_control.privacy import sanitize_text, workspace_roots  # noqa: E402
from scripts.execution_control.process_tree import ProcessResult  # noqa: E402


def _plan(**overrides) -> ExecutionPlan:
    defaults = dict(
        run_id="token-privacy-run",
        execution_id="ci:pytest",
        profile_id="ci-pytest",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        expected_seconds=1.0,
        soft_seconds=2.0,
        stall_seconds=None,
        hard_seconds=5.0,
        diagnostic_hard_seconds=2.0,
        termination_grace_seconds=0.2,
        progress_contract_id=None,
        termination_policy_id="owned-process-group",
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        admission_decision="run",
        context_signature="test",
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


def _runtime_secrets() -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    hex_token = secrets.token_hex(24)
    return {
        "bearer": f"Bearer {token}",
        "basic": f"Basic {secrets.token_urlsafe(16)}",
        "sk": f"sk_live_{token}",
        "ghp": f"ghp_{hex_token}",
        "api_key": f"API_KEY={token}",
        "url": f"https://user:{token}@example.com/path",
        "raw_token": token,
    }


def test_runtime_generated_tokens_redacted_from_sanitizer(isolated_state_dir):
    del isolated_state_dir
    values = _runtime_secrets()
    raw = " ".join(values.values())
    redacted = sanitize_text(raw, workspace_roots=workspace_roots(public_root=ROOT))
    for value in values.values():
        if len(value) > 20:
            assert value not in redacted
    assert "[REDACTED]" in redacted


def test_timeout_bundle_excludes_runtime_secrets(isolated_state_dir):
    del isolated_state_dir
    values = _runtime_secrets()
    payload = " ".join(values.values())
    result = ProcessResult(
        exit_code=124,
        duration_seconds=1.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail=payload,
        stderr_tail=values["bearer"],
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    bundle = collect_timeout_bundle(
        plan=_plan(),
        result=result,
        active_child="ci:pytest",
        timeout_kind="hard",
        public_root=ROOT,
    )
    if bundle.path is None:
        assert bundle.incomplete
        return
    text = Path(bundle.path).read_text(encoding="utf-8")
    for key, value in values.items():
        if len(value) >= 16:
            assert value not in text, f"{key} leaked into diagnostic bundle"


def test_history_span_stores_redacted_reference(isolated_state_dir, history):
    del isolated_state_dir
    values = _runtime_secrets()
    record = SpanRecord(
        run_id="token-span",
        span_id="token-span-id",
        parent_span_id=None,
        execution_id="ci:pytest",
        profile_id="ci-pytest",
        normalized_signature="sig" * 8,
        workload_fingerprint="wf" * 8,
        policy_fingerprint="pf" * 8,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:00:01Z",
        duration_seconds=1.0,
        exit_code=124,
        status="timeout-hard",
        expected_seconds=1.0,
        soft_seconds=2.0,
        stall_seconds=None,
        hard_seconds=5.0,
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        progress_event_count=0,
        maximum_progress_gap=0.0,
        active_child_at_end="ci:pytest",
        accepted_for_learning=False,
        quarantine_reason="timeout-hard",
        diagnostic_bundle=sanitize_text(
            values["raw_token"], workspace_roots=workspace_roots(public_root=ROOT)
        ),
    )
    history.insert_span(record, context_signature="test")
    with history._connect() as connection:
        row = connection.execute(
            "SELECT diagnostic_bundle FROM spans WHERE span_id = ?",
            ("token-span-id",),
        ).fetchone()
    assert row is not None
    assert values["raw_token"] not in row["diagnostic_bundle"]
