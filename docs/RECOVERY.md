# Recovery

spell-sync protects dictionary writes with backups, a transaction journal, and `spell-sync recover`.
There is **one** journal schema (version **2**); older or corrupt journals are rejected.

## Beginner path

If something went wrong while updating apps:

1. Open the dashboard and look for **Review recovery**, or run `spell-sync recover`.
2. If recovery is not offered and you only want to reverse a **successful** Push, there is no
   `rollback` command — see [I pushed and want to undo it](TROUBLESHOOTING.md#i-pushed-and-want-to-undo-it).
3. For a safe diagnostic export without your words, run `spell-sync support-report`.

The sections below are the technical Recovery contract (journal, lock, backups).

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

- Existing file matches **pre-image** (`hash_before`) → skip (unchanged since transaction)
- Existing file matches **post-image** (`hash_after`) → restore snapshot (roll back the write)
- Destination missing with a valid snapshot → restore from snapshot
- Created-during-transaction file still matching `hash_after` → remove it
- Otherwise → **conflict** (manual fix required)

## Lock file

`.spell-sync.lock` uses an exclusive project lock (`flock` on Unix; `msvcrt.locking` on
Windows). Only one mutating command per wordlist project at a time.
Stale PID metadata does not override a free lock.

The lock path is opened through `secure_artifacts`: symlinks, junctions, and reparse points are
rejected; only a regular file in the project directory is written.

## Internal artifact security

| Artifact | Protection |
|----------|------------|
| `.spell-sync.lock` | No-follow open; regular file only |
| `.spell-sync.journal.json` | Unique temp, fsync, atomic replace, parent dir sync (POSIX) |
| `.spell-sync.txn/` | Directory containment; snapshot files created exclusively; cleanup via descriptor-relative `remove_trusted_tree` (no `shutil.rmtree`) |

On abort, **incomplete rollback always preserves** journal and snapshots even when journal update
or cleanup fails. Journal begin failure before target writes removes snapshots when safe, or reports
remaining recovery materials with `recovery_required=true`.

Durability: atomic visibility and process-crash safety are guaranteed; power-loss durability is best
effort (file + directory sync). Residual **R-DUR** tracks missing physical power-loss / fsync proof.
See [ADR 0005](decisions/0005-secure-internal-artifacts.md). **R-PWR** is unrelated (coverage-padding
inventory debt).

## Fail closed

- String booleans in JSON (`"false"`) → corrupt journal
- Snapshot paths outside `.spell-sync.txn/` → corrupt journal
- Unsupported `schema_version` → unsupported journal (not auto-migrated)

Use `doctor --json` for machine-readable journal and drift status.
