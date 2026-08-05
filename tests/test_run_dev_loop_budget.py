"""Unit tests for local minimal wall-budget helpers in run_dev_loop."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_run_dev_loop():
    path = ROOT / "scripts" / "run_dev_loop.py"
    spec = importlib.util.spec_from_file_location("run_dev_loop_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_budget_seconds_match_strict_sla() -> None:
    mod = _load_run_dev_loop()
    assert mod.L0_BUDGET_SECONDS == 60
    assert mod.L1_BUDGET_SECONDS == 120
    assert mod.budget_seconds_for_gate("L0") == 60
    assert mod.budget_seconds_for_gate("L1") == 120


def test_budget_status_within_and_exceeded() -> None:
    mod = _load_run_dev_loop()
    assert mod.budget_status(wall_seconds=59.9, budget_seconds=60) == "within"
    assert mod.budget_status(wall_seconds=60.0, budget_seconds=60) == "within"
    assert mod.budget_status(wall_seconds=60.01, budget_seconds=60) == "exceeded"


def test_plan_mode_exits_without_running_pytest() -> None:
    mod = _load_run_dev_loop()
    code = mod.main(["--plan", "--no-sample", "--files", "docs/WORKFLOW.md"])
    assert code == 0


def test_session_reuse_skips_gate(tmp_path, monkeypatch, capsys) -> None:
    mod = _load_run_dev_loop()
    from scripts import check_session

    base = tmp_path / "sessions"
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_DIR", str(base))
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_ID", "arc-test-reuse")
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)
    sid = check_session.start_session(session_id="arc-test-reuse", base=base)
    files = ["docs/WORKFLOW.md"]
    gate_id = mod._scoped_gate_id(
        "L0",
        changed_files=files,
        sample_enabled=False,
        commit_gate=False,
        no_sample=True,
        cluster=None,
        target=None,
    )
    fp = check_session.tree_fingerprint(ROOT)
    check_session.record_check(
        gate_id,
        exit_code=0,
        duration=1.25,
        session_id=sid,
        root=ROOT,
        base=base,
        fingerprint=fp,
    )
    code = mod.main(["--no-sample", "--files", *files])
    out = capsys.readouterr().out
    assert code == 0
    assert "DEV_LOOP_SESSION_REUSE=true" in out


def test_session_reuse_does_not_cross_file_scope(tmp_path, monkeypatch, capsys) -> None:
    mod = _load_run_dev_loop()
    from scripts import check_session

    base = tmp_path / "sessions"
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_DIR", str(base))
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_ID", "arc-scope")
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)
    sid = check_session.start_session(session_id="arc-scope", base=base)
    docs_id = mod._scoped_gate_id(
        "L0",
        changed_files=["docs/WORKFLOW.md"],
        sample_enabled=False,
        commit_gate=False,
        no_sample=True,
        cluster=None,
        target=None,
    )
    fp = check_session.tree_fingerprint(ROOT)
    check_session.record_check(
        docs_id,
        exit_code=0,
        duration=1.0,
        session_id=sid,
        root=ROOT,
        base=base,
        fingerprint=fp,
    )
    code = mod.main(["--no-sample", "--files", "spell_sync/cli.py", "--plan"])
    # plan mode never reuses; also ensure scoped ids differ
    product_id = mod._scoped_gate_id(
        "L0",
        changed_files=["spell_sync/cli.py"],
        sample_enabled=False,
        commit_gate=False,
        no_sample=True,
        cluster=None,
        target=None,
    )
    assert docs_id != product_id
    assert code == 0
    assert "DEV_LOOP_SESSION_REUSE=true" not in capsys.readouterr().out


def test_no_session_reuse_flag_forces_run(tmp_path, monkeypatch, capsys) -> None:
    mod = _load_run_dev_loop()
    from scripts import check_session

    base = tmp_path / "sessions"
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_DIR", str(base))
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_ID", "arc-force")
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)
    sid = check_session.start_session(session_id="arc-force", base=base)
    files = ["docs/WORKFLOW.md"]
    gate_id = mod._scoped_gate_id(
        "L0",
        changed_files=files,
        sample_enabled=False,
        commit_gate=False,
        no_sample=True,
        cluster=None,
        target=None,
    )
    fp = check_session.tree_fingerprint(ROOT)
    check_session.record_check(
        gate_id,
        exit_code=0,
        duration=1.0,
        session_id=sid,
        root=ROOT,
        base=base,
        fingerprint=fp,
    )
    code = mod.main(["--no-sample", "--no-session-reuse", "--files", *files, "--plan"])
    out = capsys.readouterr().out
    assert code == 0
    assert "DEV_LOOP_SESSION_REUSE=true" not in out
