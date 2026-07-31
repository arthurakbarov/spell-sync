# Mutation safety

Pull, Push, Recovery, setup, and target settings updates share one mutation lifecycle. This
document summarizes application-level contracts; operational detail lives in
[RECOVERY.md](../RECOVERY.md).

## Lifecycle

```text
preview (immutable prepared plan + RuntimeIdentity)
  → user confirmation (plan/update ID)
  → operation lock (.spell-sync.lock)
  → fresh runtime + identity under lock
  → identity/fingerprint comparison with preview
  → transaction / journal / writes
  → history summary (no user words)
```

## Invariants

| Rule | Detail |
|------|--------|
| No stale preview execution | Changed runtime or fingerprint after preview → safe stop |
| No automatic replan | User must run preview again |
| Pending Recovery blocks writes | New Pull/Push/Recovery blocked until resolved |
| Operation lock | One mutating operation per project at a time |
| Atomic dictionary writes | Snapshots + journal v2 + rollback paths |
| Privacy | User words never stored in history or technical logs |
| TUI boundary | No subprocess CLI; no direct dictionary/journal writers |

## Prepared objects

| Type | Role |
|------|------|
| `PreparedPush` | Push plan bound to preview identity |
| `PullPreview` / `PushPreview` | Immutable preview DTOs |
| `PreparedTargetSettingsUpdate` | Config-only target settings preview |
| `PreparedProjectSetup` | Setup preview |

Confirmation tokens (`confirmed_plan_id`, `confirmed_update_id`, etc.) are separate execution
arguments — not embedded in request DTOs.

## Where to read more

- Journal schema and recovery commands: [RECOVERY.md](../RECOVERY.md)
- Transaction implementation: `push_transaction.py`, `push_journal.py`
- Tests: `tests/test_pull_safety.py`, `tests/test_transaction_safety.py`,
  `tests/test_tui_mutation_safety.py`
