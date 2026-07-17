# Recovery

spell-sync protects dictionary writes with backups, a transaction journal, and `spell-sync recover`.
There is **one** journal schema (version **2**); older or corrupt journals are rejected.

## When to use what

| Situation | Command |
|-----------|---------|
| Push interrupted (crash, kill) | `spell-sync recover` |
| Unsure what happened | `spell-sync doctor` |
| Journal file is corrupt | Fix manually or `recover --discard-corrupt-journal` (destructive) |

Push may also leave rotating `.bak` files beside dictionaries (`[io] backup_keep`). There is no
`rollback` CLI — restore from `.bak` manually if you need a pre-push copy outside the journal.

## Journal files

After a mutating push starts, spell-sync may leave:

- `.spell-sync.journal.json` — transaction state
- `.spell-sync.txn/<uuid>/` — content snapshots for recovery

Journal states:

| State | Meaning |
|-------|---------|
| `writing` | Push in progress or interrupted |
| `completed` | Push finished; journal may remain until cleanup |
| `rollback_incomplete` | Internal rollback failed partway; snapshots preserved |

Successful **`recover --yes`** removes the journal and snapshot directory. Conflicts or partial
recovery preserve them for a later attempt.

## Transaction recovery (`recover`)

```bash
spell-sync recover              # inspect
spell-sync recover --dry-run    # show planned actions
spell-sync recover --yes        # restore without prompt
spell-sync recover --json
```

Recovery compares on-disk file hashes to journal `hash_before` / `hash_after`:

- Existing file matches **post-image** → already OK
- Existing file matches **pre-image** → skip (unchanged since transaction)
- Missing or matching snapshot → restore from snapshot
- Otherwise → **conflict** (manual fix required)

## Lock file

`.spell-sync.lock` uses kernel `flock`. Only one mutating command per wordlist project at a time.
Stale PID metadata does not override a free lock.

## Fail closed

- String booleans in JSON (`"false"`) → corrupt journal
- Snapshot paths outside `.spell-sync.txn/` → corrupt journal
- Unsupported `schema_version` → unsupported journal (not auto-migrated)

Use `doctor --json` for machine-readable journal and drift status.
