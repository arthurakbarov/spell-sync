"""Shared TUI layout contract tests."""

from textual.widgets import Button

from spell_sync.tui.layout import action_bar, expected_duration_hint


def test_expected_duration_hint_uses_five_second_threshold() -> None:
    assert expected_duration_hint("dashboard") is None
    assert expected_duration_hint("history_load") == "Usually takes about 5 seconds."


def test_action_bar_has_shared_id() -> None:
    bar = action_bar(Button("Back", id="btn-back"))

    assert bar.id == "screen-actions"
