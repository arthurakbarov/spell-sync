"""Setup target selection helpers for the setup wizard."""

from __future__ import annotations

from dataclasses import dataclass

from .discovery import SetupTarget, SetupTargetDiscovery


@dataclass(frozen=True)
class SetupSelection:
    selected_target_ids: frozenset[str]


def default_selection(discovery: SetupTargetDiscovery) -> SetupSelection:
    return SetupSelection(
        selected_target_ids=frozenset(
            target.identifier
            for target in discovery.targets
            if target.enabled_by_default and target.selectable
        )
    )


def merge_selection_after_refresh(
    previous: SetupSelection,
    previous_target_ids: frozenset[str],
    discovery: SetupTargetDiscovery,
) -> SetupSelection:
    selectable = {target.identifier for target in discovery.targets if target.selectable}
    kept = previous.selected_target_ids & selectable
    current_ids = {target.identifier for target in discovery.targets}
    new_target_ids = current_ids - previous_target_ids
    new_defaults = {
        target.identifier
        for target in discovery.targets
        if target.identifier in new_target_ids and target.enabled_by_default and target.selectable
    }
    return SetupSelection(selected_target_ids=frozenset(kept | new_defaults))


def toggle_target(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
    target_id: str,
) -> SetupSelection:
    target = _target_by_id(discovery, target_id)
    if target is None or not target.selectable:
        return selection
    selected = set(selection.selected_target_ids)
    if target_id in selected:
        selected.remove(target_id)
    else:
        selected.add(target_id)
    return SetupSelection(selected_target_ids=frozenset(selected))


def select_available_targets(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
) -> SetupSelection:
    selected = set(selection.selected_target_ids)
    for target in discovery.targets:
        if target.selectable:
            selected.add(target.identifier)
    return SetupSelection(selected_target_ids=frozenset(selected))


def clear_selectable_targets(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
) -> SetupSelection:
    disabled = {
        target.identifier
        for target in discovery.targets
        if not target.selectable and target.identifier in selection.selected_target_ids
    }
    return SetupSelection(selected_target_ids=frozenset(disabled))


def selection_tuple(selection: SetupSelection) -> tuple[str, ...]:
    return tuple(sorted(selection.selected_target_ids))


def _target_by_id(discovery: SetupTargetDiscovery, target_id: str) -> SetupTarget | None:
    for target in discovery.targets:
        if target.identifier == target_id:
            return target
    return None
