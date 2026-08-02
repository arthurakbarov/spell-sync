"""Regression tests for phase-10 approval-readiness tracker guards."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-docs-contract.py"
_spec = importlib.util.spec_from_file_location("check_docs_contract", SCRIPT)
assert _spec and _spec.loader
docs_contract = importlib.util.module_from_spec(_spec)
sys.modules["check_docs_contract"] = docs_contract
_spec.loader.exec_module(docs_contract)

TRACKER = ROOT / "docs" / "ARCHITECTURE_0_3_IMPLEMENTATION.md"


def test_p1_corrective_not_in_progress() -> None:
    text = TRACKER.read_text(encoding="utf-8")
    _, body = docs_contract._current_phase_body(text)
    assert docs_contract._CORRECTIVE_IN_PROGRESS.search(body) is None


def test_p2_no_owner_approved_while_awaiting() -> None:
    violations = docs_contract._check_phase_tracker_readiness(ROOT)
    ids = {v.check_id for v in violations}
    assert "PHASE-017" not in ids


def test_p5_no_release_published_claim() -> None:
    violations = docs_contract._check_phase_tracker_readiness(ROOT)
    ids = {v.check_id for v in violations}
    assert "PHASE-018" not in ids


def test_p6_valid_pending_approval_state() -> None:
    violations = docs_contract._check_phase_tracker_readiness(ROOT)
    ids = {v.check_id for v in violations}
    assert "PHASE-021" not in ids


def test_phase_tracker_readiness_passes() -> None:
    violations = docs_contract._check_phase_tracker_readiness(ROOT)
    assert violations == []
