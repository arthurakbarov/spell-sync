"""Shared helpers for operation-history compaction tests."""

from __future__ import annotations

COMPACTION_HISTORY_CAP = 8
HISTORY_CAP_TARGET = "spell_sync.diagnostics.history_store.MAX_HISTORY_RECORDS"


def install_history_record_cap(monkeypatch, *, cap: int = COMPACTION_HISTORY_CAP) -> int:
    """Cap MAX_HISTORY_RECORDS so compaction tests stay fast."""
    monkeypatch.setattr(HISTORY_CAP_TARGET, cap)
    return cap
