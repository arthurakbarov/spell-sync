# Architecture

spell-sync keeps one **canonical personal wordlist** as source of truth and **pushes** it to
discovered **application custom dictionary** files. **Pull** merges words from custom
dictionaries into the wordlist (union only — deletions require editing the wordlist and
pushing).

## Wordlist model

Let:

```text
W  = canonical personal wordlist (personal spelling exceptions)
Cᵢ = custom dictionary words for enabled target i
Bᵢ = built-in dictionary for target i (outside Spell Sync)
```

**Pull** (case-insensitive union):

```text
W' = W ∪ C₁ ∪ C₂ ∪ ... ∪ Cₙ
```

**Push** for a target without script filtering:

```text
Cᵢ' = W
```

**Push** when target i applies a subset filter (for example Windows locale custom files):

```text
Cᵢ' = filterᵢ(W)
```

**Invariants:**

- `Bᵢ` is not read, modified, or used when planning Pull or Push.
- `W ∩ Bᵢ` may be non-empty in real life. Storing a word in `Cᵢ` even when the application
  already recognizes it via `Bᵢ` is intentional redundancy and is safe.
- Spell Sync does not guarantee spell-check behavior beyond writing `Cᵢ'`; applications may
  impose additional constraints.

Targets with subset filtering today: Windows custom spelling files (`win-ru` → Cyrillic subset,
`win-en` / `win-en-gb` → Latin subset). macOS custom spelling files receive the full wordlist.

## Command flow

```text
CLI parser (CliOptions)
    ↓
cli_request_adapter
    ↓
immutable application request
    ↓
SpellSyncService

TUI controller
    ↓
immutable application request
    ↓
SpellSyncService
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
Structured result → human or JSON (CLI/TUI presentation)
```

Runtime settings are resolved explicitly via `RuntimeResolver` (Phase 3). There is no
production `ContextVar` scope and no module-level config cache; mutating commands resolve
fresh runtime under the operation lock.

Mutating operations emit typed **technical events** (`EventId`, `TechnicalEvent`) through a
single `EventEmitter` path. Presentation copy is produced at CLI/TUI boundaries only
(`event_presenter.py`); the rotating technical log stores privacy-safe JSON Lines records
(`schemaVersion: 1`) as **exact JSON objects per line** (no stdlib log prefix on structured
records). Metadata fields (`CorrelationId`, `TargetId`, `EventReason`, `TerminalOutcome`) are
validated before serialization. See ADR `docs/decisions/0004-structured-technical-events.md`.

## Core modules

| Module | Role |
|--------|------|
| `cli.py` | Argparse, command dispatch |
| `cli_options.py` | CLI parser DTO only |
| `cli_request_adapter.py` | Map `CliOptions` → application requests |
| `application/requests.py` | Immutable UI-neutral request dataclasses |
| `application/service.py` | Facade for CLI and TUI |
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
