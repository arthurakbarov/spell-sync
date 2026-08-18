"""Setup target selection helpers for the setup wizard."""

from dataclasses import dataclass, replace

from .discovery import SetupTarget, SetupTargetDiscovery, dictionary_family_id


@dataclass(frozen=True)
class SetupSelection:
    selected_target_ids: frozenset[str]
    # Exact dictionary names excluded while their family stays selected.
    excluded_dictionary_names: frozenset[str] = frozenset()


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
    current_ids = {target.identifier for target in discovery.targets}
    kept_selectable = previous.selected_target_ids & selectable
    # Keep non-selectable rows that remain in discovery and were already selected
    # (e.g. currently unreadable but still enabled in config). Matches
    # selection_from_enabled / clear_selectable_targets / resolve_enabled_targets.
    kept_non_selectable = {
        target.identifier
        for target in discovery.targets
        if (
            not target.selectable
            and target.identifier in previous.selected_target_ids
            and target.identifier in current_ids
        )
    }
    new_target_ids = current_ids - previous_target_ids
    new_defaults = {
        target.identifier
        for target in discovery.targets
        if target.identifier in new_target_ids and target.enabled_by_default and target.selectable
    }
    known_dictionary_names = {
        name for target in discovery.targets for name, _count in target.dictionary_word_counts
    }
    kept_excluded = previous.excluded_dictionary_names & known_dictionary_names
    return SetupSelection(
        selected_target_ids=frozenset(kept_selectable | kept_non_selectable | new_defaults),
        excluded_dictionary_names=kept_excluded,
    )


def toggle_target(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
    target_id: str,
) -> SetupSelection:
    target = _target_by_id(discovery, target_id)
    if target is None or not target.selectable:
        return selection
    selected = set(selection.selected_target_ids)
    excluded = set(selection.excluded_dictionary_names)
    if target_id in selected:
        selected.remove(target_id)
        # Drop excludes for a disabled family — family off is enough.
        family_names = {name for name, _count in target.dictionary_word_counts}
        excluded -= family_names
    else:
        selected.add(target_id)
    return SetupSelection(
        selected_target_ids=frozenset(selected),
        excluded_dictionary_names=frozenset(excluded),
    )


def toggle_dictionary_inclusion(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
    dictionary_name: str,
) -> SetupSelection:
    """Include/exclude one dictionary file inside an enabled family."""
    family_id = dictionary_family_id(dictionary_name)
    target = _target_by_id(discovery, family_id)
    if target is None:
        return selection
    known = {name for name, _count in target.dictionary_word_counts}
    if dictionary_name not in known:
        return selection
    if family_id not in selection.selected_target_ids:
        return selection
    if len(known) <= 1:
        # Single-dictionary families use the family checkbox only.
        return selection
    excluded = set(selection.excluded_dictionary_names)
    if dictionary_name in excluded:
        excluded.remove(dictionary_name)
    else:
        # Keep at least one dictionary included in an enabled family.
        included = known - excluded
        if included == {dictionary_name}:
            return selection
        excluded.add(dictionary_name)
    return replace(selection, excluded_dictionary_names=frozenset(excluded))


def select_available_targets(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
) -> SetupSelection:
    selected = set(selection.selected_target_ids)
    for target in discovery.targets:
        if target.selectable:
            selected.add(target.identifier)
    # Select available means every discovered dictionary participates.
    return SetupSelection(
        selected_target_ids=frozenset(selected),
        excluded_dictionary_names=frozenset(),
    )


def clear_selectable_targets(
    selection: SetupSelection,
    discovery: SetupTargetDiscovery,
) -> SetupSelection:
    disabled = {
        target.identifier
        for target in discovery.targets
        if not target.selectable and target.identifier in selection.selected_target_ids
    }
    return SetupSelection(
        selected_target_ids=frozenset(disabled),
        excluded_dictionary_names=frozenset(),
    )


def selection_from_enabled(
    discovery: SetupTargetDiscovery,
    enabled_target_ids: frozenset[str],
    *,
    excluded_dictionary_names: frozenset[str] = frozenset(),
) -> SetupSelection:
    known_dictionary_names = {
        name for target in discovery.targets for name, _count in target.dictionary_word_counts
    }
    return SetupSelection(
        selected_target_ids=frozenset(
            target.identifier
            for target in discovery.targets
            if target.identifier in enabled_target_ids
        ),
        excluded_dictionary_names=frozenset(
            name for name in excluded_dictionary_names if name in known_dictionary_names
        ),
    )


def selection_tuple(selection: SetupSelection) -> tuple[str, ...]:
    return tuple(sorted(selection.selected_target_ids))


def _target_by_id(discovery: SetupTargetDiscovery, target_id: str) -> SetupTarget | None:
    for target in discovery.targets:
        if target.identifier == target_id:
            return target
    return None
