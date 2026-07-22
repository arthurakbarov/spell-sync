"""HistoryStore connection lifecycle."""

from __future__ import annotations

import sqlite3
import warnings


def test_connect_closes_after_success(isolated_state_dir, history_store):
    del isolated_state_dir
    history_store.insert_span(
        __import__("tests.conftest_execution", fromlist=["make_span_record"]).make_span_record(),
        context_signature="ctx" * 8,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        with history_store._connect() as connection:
            connection.execute("SELECT 1").fetchone()
    assert not any(issubclass(item.category, ResourceWarning) for item in caught)


def test_history_store_context_manager_closes_held_connection(isolated_state_dir, history_store):
    del isolated_state_dir
    with history_store:
        history_store._held_connection = sqlite3.connect(":memory:")
    assert history_store._held_connection is None
