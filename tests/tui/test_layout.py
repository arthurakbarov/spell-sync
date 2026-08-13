"""Shared TUI layout contract tests."""

from textual.widgets import Button

from spell_sync.tui.layout import (
    action_bar,
    expected_duration_hint,
    menu_item,
    targets_inline_actions,
)


def test_expected_duration_hint_uses_five_second_threshold() -> None:
    assert expected_duration_hint("dashboard") is None
    assert expected_duration_hint("history_load") == "Usually takes about 5 seconds."


def test_action_bar_has_shared_id() -> None:
    bar = action_bar(Button("Back", id="btn-back"))

    assert bar.id == "screen-actions"
    assert "screen-actions" in bar.classes


def test_targets_inline_actions_embeds_equal_stack() -> None:
    stack = targets_inline_actions(primary_label="Continue", primary_id="btn-continue")

    assert stack.id == "targets-actions"
    assert "screen-actions" in stack.classes
    assert "targets-inline-actions" in stack.classes


def test_menu_item_classes() -> None:
    with_hint = menu_item(Button("Go", id="btn-go"), "Does the thing.", hint_id="go-hint")
    bare = menu_item(Button("Quit", id="btn-quit"))

    assert "menu-item" in with_hint.classes
    assert "menu-item" in bare.classes


def test_section_label_uses_rule_prefix() -> None:
    from spell_sync.tui.layout import section_label

    label = section_label("Usual path")
    assert "section-label" in label.classes
    assert str(label.render()).startswith("── ")


def test_sync_data_table_rows_hides_empty() -> None:
    from spell_sync.tui.layout import sync_data_table_rows

    class _FakeTable:
        def __init__(self, row_count: int = 0) -> None:
            self.row_count = row_count
            self.display = True
            self.classes: set[str] = set()

        def set_class(self, add: bool, *names: str) -> None:
            for name in names:
                if add:
                    self.classes.add(name)
                else:
                    self.classes.discard(name)

    empty = _FakeTable()
    sync_data_table_rows(empty)  # type: ignore[arg-type]
    assert empty.display is False
    assert "-populated" not in empty.classes

    filled = _FakeTable(3)
    sync_data_table_rows(filled)  # type: ignore[arg-type]
    assert filled.display is True
    assert "-populated" in filled.classes
