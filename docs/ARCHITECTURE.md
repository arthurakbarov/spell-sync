# Architecture

spell-sync keeps one **wordlist** as source of truth and **pushes** it to discovered dictionary
files. **Pull** merges words from dictionaries into the wordlist (union only — deletions require
editing the wordlist and pushing).

## Command flow

```text
CLI parsing
    ↓
ValidatedRuntime (config + journal, under lock)
    ↓
SyncRun / command logic
    ↓
PreparedPush (immutable plan for push)
    ↓
Safety checks + confirmation
    ↓
Transactional execution (journal + snapshots)
    ↓
Structured result → human or JSON
```

## Core modules

| Module | Role |
|--------|------|
| `cli.py` | Argparse, command dispatch |
| `commands.py` | `pull`, `push`, `status`, `init`, `lint` |
| `sync_context.py` | `RuntimeContext` — wordlist, config, dictionaries |
| `validated_runtime.py` | Single config/journal load under lock |
| `sync_run.py` | Dictionary reads, diffs, push/pull orchestration |
| `push_prepared.py` | Immutable `PreparedPush` plan |
| `push_render.py` | Pre-compute `hash_after` payloads |
| `push_transaction.py` | Snapshots, atomic writes |
| `push_journal.py` | Journal v2 persistence and recovery |
| `journal_schema.py` | Strict journal parsing |
| `operation_lock.py` | Project-wide flock |
| `settings.py` | Strict TOML validation |

## Push transaction

1. Build plan from wordlist + dictionary read results (single read per file).
2. Confirm removals / running apps (unless `--yes` / dry-run).
3. Create `.spell-sync.txn/<uuid>/` snapshots.
4. Write journal (`state: writing`) with `hash_before` / `hash_after`.
5. Atomic replace per target; update journal per target/wordlist WAH flags.
6. Complete journal or rollback on failure; `rollback_incomplete` preserves artifacts.

## Config

Strict TOML only — see [CONFIGURATION.md](CONFIGURATION.md). Invalid files must be fixed or
recreated; there is no automatic config upgrade path.

## JSON

Envelope `schema_version: 1` on all `--json` output. Journal internal schema is **v2** (separate).

## Testing

100% line coverage on `spell_sync/` enforced in CI. Regression tests for transaction safety live
in `tests/test_transaction_safety.py` and `tests/test_push_safety_coverage.py`.
