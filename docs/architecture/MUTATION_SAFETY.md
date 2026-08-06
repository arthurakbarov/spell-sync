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
| Missing-target absence | Push targets missing at preview must still be absent at write (`fingerprint is None` → continued absence check) |
| Recovery confirmation binding | Recovery confirmations bind to the reviewed journal **content digest**, not only the transaction id |
| No automatic replan | User must run preview again |
| Pending Recovery blocks new writes | New Pull/Push/setup/target-settings blocked until Recovery resolves the pending journal; Recovery itself is allowed. Setup and target-settings **re-check journal status under the operation lock** before writing |
| Operation lock | One mutating operation per project at a time |
| Internal artifact containment | `.spell-sync.lock`, journal, and `.spell-sync.txn` paths reject symlinks/reparse points and stay under the project root via `secure_artifacts` (best-effort on Windows reparse/junction — see R-WIN). Recovery restores use unique temps (no predictable `.recover-tmp` symlink target) |
| Rollback precedence | Incomplete rollback preserves journal and snapshots regardless of journal update or cleanup errors |
| Durability | Journal publication fsyncs temp file and parent directory (POSIX best effort); physical power-loss / fsync durability proof not claimed (R-DUR) |
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
- Transaction implementation: `push_transaction.py`, `push_journal.py`, `secure_artifacts.py`
- Tests: `tests/test_pull_safety.py`, `tests/test_transaction_safety.py`,
  `tests/test_tui_mutation_safety.py`, `tests/test_internal_artifact_security.py`,
  `tests/test_secure_artifacts.py`
- ADR: [0005-secure-internal-artifacts.md](../decisions/0005-secure-internal-artifacts.md)
