---
name: tui-flow
description: >-
  Add or change a TUI screen or navigation flow. Use when modifying spell_sync/tui/
  screens, controller routing, or TUI tests. Ensures service facade, workers, and
  safety tests.
---

# TUI flow

## When to use

- New or modified Textual screen
- Controller navigation or session state changes
- TUI test additions

## Do not use

- For CLI-only changes
- To bypass `SpellSyncService` with direct filesystem calls

## Workflow

1. Find the existing controller/service path in `spell_sync/tui/controller.py` and `@docs/TUI_IMPLEMENTATION.md`.
2. Describe navigation: entry screen → actions → exit/report.
3. Classify read-only vs mutation — mutations go through `OperationScreen` + service execute methods.
4. Use `SpellSyncService` facade — never import writers or invoke CLI via subprocess.
5. Long operations: Textual `@work` worker; use `LoadTokenMixin` for stale-result suppression.
6. Apply existing cancellation policy — no worker kill after lock/transaction start.
7. Keyboard (`Space`, arrows), mouse toggle, and **80×24** layout.
8. Controlled error states — no tracebacks in UI.

## Tests

```bash
python3.11 -m pytest tests/tui/test_<screen>.py -q
python3.11 -m pytest tests/tui/test_architecture.py -q
```

- Ordinary flows: `tests/tui/fake_service.py`
- Safety integration: real core with synthetic fixtures when mutation involved

## Stop conditions

- Navigation documented
- Architecture tests pass (no writer imports in TUI)
- Focused TUI tests green

## Final report

- Screen map delta
- Read-only vs mutation classification
- Tests added/updated
- Manual verification: keyboard, mouse, narrow terminal

## Finalize workspace snapshot

Modifying tasks only — before the final report: skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`; canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`. SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
