"""Shared operation dependencies for application services.

Single import surface for symbols tests patch under the legacy
``spell_sync.application.service`` path. Focused services import from here so
``unittest.mock.patch`` targets stay stable across the Phase 4 decomposition.
"""

from __future__ import annotations

from ..health.report import build_doctor_report
from ..operation_lock import read_active_operation_lock
from ..push_journal import (
    cleanup_after_successful_recovery,
    discard_completed_journal,
    file_content_hash,
    load_journal_result,
    recover_from_journal,
    safe_discard_journal_file,
)
from ..push_prepared import execute_prepared_push, plan_fingerprint_conflict
from .builders import build_doctor_snapshot, build_pull_preview, build_status_detail_snapshot

__all__ = (
    "build_doctor_report",
    "build_doctor_snapshot",
    "build_pull_preview",
    "build_status_detail_snapshot",
    "cleanup_after_successful_recovery",
    "discard_completed_journal",
    "execute_prepared_push",
    "file_content_hash",
    "load_journal_result",
    "plan_fingerprint_conflict",
    "read_active_operation_lock",
    "recover_from_journal",
    "safe_discard_journal_file",
)
