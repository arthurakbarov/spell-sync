"""Timeout diagnostics tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.execution_control.diagnostics import _redact, collect_timeout_bundle
from scripts.execution_control.models import ExecutionPlan
from scripts.execution_control.paths import timeout_bundle_dir
from scripts.execution_control.process_tree import ProcessResult


def _plan(**overrides) -> ExecutionPlan:
    defaults = dict(
        run_id="diag-run",
        execution_id="ci:pytest",
        profile_id="ci-child",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        diagnostic_hard_seconds=10.0,
        termination_grace_seconds=5.0,
        progress_contract_id=None,
        termination_policy_id="owned-process-group",
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        admission_decision="run",
        context_signature="macos|3.11|full-ci|501+|cov1|tui0|pkg0|unknown",
    )
    return ExecutionPlan(**defaults)


def test_redact_sensitive_sentinels():
    raw = (
        "word SENSITIVE_USER_WORD_7f3a token secret-token-value "
        "path /Users/private-user cfg raw-spell-sync-config"
    )
    redacted = _redact(raw)
    assert "SENSITIVE_USER_WORD_7f3a" not in redacted
    assert "secret-token-value" not in redacted
    assert "/Users/private-user" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_truncates_long_output():
    assert len(_redact("x" * 10000)) <= 8000


def test_timeout_bundle_redacts_private_sentinels(isolated_state_dir):
    del isolated_state_dir
    result = ProcessResult(
        exit_code=124,
        duration_seconds=1.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail="SENSITIVE_USER_WORD_7f3a /Users/private-user secret-token-value",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    path = collect_timeout_bundle(
        plan=_plan(),
        result=result,
        active_child="ci:pytest",
        timeout_kind="hard",
    )
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    text = json.dumps(payload)
    assert "SENSITIVE_USER_WORD_7f3a" not in text
    assert "/Users/private-user" not in text
    assert "[REDACTED]" in text
    assert timeout_bundle_dir("diag-run").is_dir()


def test_diagnostic_collector_respects_short_budget(isolated_state_dir, monkeypatch):
    del isolated_state_dir
    import scripts.execution_control.diagnostics as diagnostics

    original_bounded = diagnostics._run_bounded

    def _inject_failure(**kwargs):
        if kwargs.get("name") == "owned-process-group":
            kwargs["failures"].append("owned-process-group:timeout")
            return None
        return original_bounded(**kwargs)

    monkeypatch.setattr(diagnostics, "_run_bounded", _inject_failure)
    result = ProcessResult(
        exit_code=124,
        duration_seconds=1.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail="",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    started = time.monotonic()
    path = collect_timeout_bundle(
        plan=_plan(diagnostic_hard_seconds=0.05),
        result=result,
        active_child=None,
        timeout_kind="hard",
    )
    elapsed = time.monotonic() - started
    assert elapsed < 0.35
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["collectorFailures"]
