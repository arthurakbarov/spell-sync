"""Cross-project methodology invariants shared with nix-darwin."""

from __future__ import annotations

from pathlib import Path

from scripts.ci_impact.constants import FULL_CI_CHANGE_CLASSES, NON_CI_CHANGE_CLASSES, ChangeClass
from scripts.validate_commit_messages import CommitMessage, validate_message
from scripts.validate_status_contract import validate as validate_status_contract

ROOT = Path(__file__).resolve().parents[1]


def test_commit_subject_shape_matches_shared_canon() -> None:
    ok = CommitMessage(sha="a" * 40, subject="Align methodology reuse tests.", body="")
    assert validate_message(ok, check_hygiene=True) == []
    bad_prefix = CommitMessage(sha="b" * 40, subject="feat: add something.", body="")
    errors = validate_message(bad_prefix, check_hygiene=True)
    assert any("Conventional Commit" in item for item in errors)
    bad_period = CommitMessage(sha="c" * 40, subject="Missing period", body="")
    assert any("end with '.'" in item for item in validate_message(bad_period, check_hygiene=False))


def test_unknown_change_class_forces_full_ci() -> None:
    assert ChangeClass.UNKNOWN in FULL_CI_CHANGE_CLASSES
    assert ChangeClass.DOCUMENTATION in NON_CI_CHANGE_CLASSES
    assert ChangeClass.AGENT_WORKFLOW in NON_CI_CHANGE_CLASSES


def test_status_contract_and_evidence_ladder_present() -> None:
    assert validate_status_contract(ROOT) == []
    contracts = (ROOT / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    assert "## Evidence levels" in contracts
    assert "package-smoked" in contracts
    workflow = (ROOT / "docs" / "WORKFLOW.md").read_text(encoding="utf-8")
    assert "## When not to rerun" in workflow


def test_no_canvas_rule_is_required() -> None:
    rule = ROOT / ".cursor" / "rules" / "no-canvas-for-text.mdc"
    text = rule.read_text(encoding="utf-8")
    assert "Absolute ban" in text or "absolute" in text.lower()
    assert "alwaysApply: true" in text
    agent_cfg = (ROOT / "scripts" / "check_agent_config.py").read_text(encoding="utf-8")
    assert "no-canvas-for-text.mdc" in agent_cfg
