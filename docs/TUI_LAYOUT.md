# TUI layout contract

Single visual system for the Textual UI. Implementers and tests follow this file
together with `spell_sync/tui/layout.py` and `spell_sync/tui/app.tcss`.

## Goals

1. One screen shell — not a mix of docked setup, broken dashboard grid, and bare buttons.
2. Actions are predictable: primary first, secondary next, Back/Cancel last.
3. Structured data uses tables; prose is short summary only.
4. Waits that usually take 5+ seconds show an expected-duration hint.

## Screen shell

```text
Header
VerticalScroll#screen-body.screen-body   ← summary + tables + forms
Vertical#screen-actions.screen-actions   ← dock bottom; equal-width buttons
  [optional Static.action-status]
  Button (primary)
  Button…
  Back | Cancel | Quit
Footer
```

- Body max width: **78** columns (80×24 terminals).
- Action buttons: shared width (**36**), stacked vertically, gap above the first button.
- Do **not** place status Statics between buttons (status goes in `.action-status` above the stack).
- Do **not** use a 2-column grid that interleaves section labels with buttons.

## Button rules

| Role | Variant | Placement |
|------|---------|-----------|
| Main next step (Run pull, Continue, Save) | `primary` | First in action bar |
| Refresh / re-run diagnostics | `default` | After primary, before Back |
| Destructive (Quit, Clear, Discard) | `error` when terminal | Last among peers; never primary for refresh |
| Back / Cancel | `default` | Always last |

Refresh must never be `primary` when a mutating continue/run button exists on the same screen.

Every dismissible screen exposes Escape → Back/Cancel (bindings or modal cancel).

## Content rules

| Data | Widget |
|------|--------|
| Target / source / check rows | `DataTable` |
| Operation history list | `DataTable` (row select opens details) |
| Short safety / direction copy | `Static` summary above the table |
| Live mutation stages | Compact stage list + `ProgressBar` (ETA when totals known) |
| Technical JSONL | Support-only; never the default Health view |

Avoid multi-page `"\n".join(lines)` dumps for tabular facts (status targets, doctor checks,
pull sources, push targets, recovery rows, history).

## Expected duration

Keys live in `EXPECTED_DURATION_SECONDS` (`spell_sync/tui/layout.py`).

- If estimate **≥ 5** seconds: show `Usually takes about N seconds.` under the loading or
  operation title (`loading_message` / `expected_duration_hint`).
- If estimate **< 5** seconds: no duration line.
- Hints are guidance, not timers; do not invent live countdowns without measured progress.

## Dashboard exception

Dashboard keeps summary and a vertical sectioned menu in one scrollable body (too many
actions to dock on 80×24). Section labels are full-width rows above their buttons — never
a 2-column grid that mixes labels into button cells. Button width still matches the
shared 36-column action style.

## Migration

New and edited screens must use `#screen-body` / `#screen-actions` (setup may keep
`.setup-body` / `.setup-actions` aliases that share the same CSS rules).
