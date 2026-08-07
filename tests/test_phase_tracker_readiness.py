"""Regression tests for phase-10 approval-readiness tracker guards."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_docs_contract as docs_contract  # noqa: E402

TRACKER = ROOT / "docs" / "ARCHITECTURE_V1_IMPLEMENTATION.md"


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


def test_p7_tip_ssot_baseline() -> None:
    violations = docs_contract._check_phase_tracker_readiness(ROOT)
    ids = {v.check_id for v in violations}
    assert "PHASE-022" not in ids
    assert "PHASE-023" not in ids
