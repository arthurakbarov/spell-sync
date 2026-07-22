"""Dynamic privacy redaction tests."""

from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

from scripts.execution_control.diagnostics import collect_timeout_bundle
from scripts.execution_control.models import ExecutionPlan, SpanRecord
from scripts.execution_control.privacy import sanitize_text, workspace_roots
from scripts.execution_control.process_tree import ProcessResult

ROOT = Path(__file__).resolve().parents[1]


def test_dynamic_home_and_token_redaction(isolated_state_dir):
    del isolated_state_dir
    token = secrets.token_urlsafe(24)
    home = str(Path.home())
    repo = str(ROOT.resolve())
    raw = f"home={home} repo={repo} token={token} url=https://user:{token}@example.com"
    redacted = sanitize_text(raw, workspace_roots=workspace_roots(public_root=ROOT))
    assert home not in redacted
    assert repo not in redacted
    assert token not in redacted
    assert "user:" not in redacted or "[REDACTED]" in redacted


def test_timeout_bundle_excludes_dynamic_home(isolated_state_dir, monkeypatch):
    del isolated_state_dir
    dynamic = f"{Path.home()}/private-{uuid.uuid4().hex}"
    result = ProcessResult(
        exit_code=124,
        duration_seconds=1.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail=f"path {dynamic}",
        stderr_tail=os.environ.get("USER", "user"),
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    plan = ExecutionPlan(
        run_id="privacy-run",
        execution_id="ci:pytest",
        profile_id="ci-child",
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
    bundle = collect_timeout_bundle(
        plan=plan,
        result=result,
        active_child="ci:pytest",
        timeout_kind="hard",
        public_root=ROOT,
    )
    if bundle.path is None:
        assert bundle.incomplete
        return
    text = Path(bundle.path).read_text(encoding="utf-8")
    assert dynamic not in text
    assert str(Path.home()) not in text


def test_history_span_stores_redacted_diagnostic_reference(isolated_state_dir, history):
    del isolated_state_dir
    home_path = str(Path.home())
    record = SpanRecord(
        run_id="privacy-span",
        span_id="privacy-span-id",
        parent_span_id=None,
        execution_id="ci:pytest",
        profile_id="ci-child",
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
            home_path, workspace_roots=workspace_roots(public_root=ROOT)
        ),
    )
    history.insert_span(record, context_signature="test")
    with history._connect() as connection:
        row = connection.execute(
            "SELECT diagnostic_bundle FROM spans WHERE span_id = ?",
            ("privacy-span-id",),
        ).fetchone()
    assert row is not None
    assert home_path not in row["diagnostic_bundle"]
