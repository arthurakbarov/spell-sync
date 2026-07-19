# TUI implementation

Developer reference for the Textual terminal UI and its relationship to the application layer.

## Architecture

```text
spell_sync/cli.py              argparse, COMMANDS dispatch, entry_point
    ↓
CliOptions                     frozen dataclass from argparse namespace
    ↓
SpellSyncService               UI-neutral facade (spell_sync/application/service.py)
    ↓
command_helpers / SyncRun      pull, push, recover, status core
project_setup/                 setup wizard + post-setup target settings
    ↓
diagnostics/                   operation history + technical logs (configured paths only)
    ↓
spell_sync/tui/                Textual app, controller, screens, workers
```

### Entry routing

| Input | TTY | Result |
|-------|-----|--------|
| `spell-sync` (no args) | yes, ready project | Dashboard |
| `spell-sync` (no args) | yes, no project | Setup wizard |
| `spell-sync` (no args) | yes, invalid project | Dashboard with blocking diagnostic |
| `spell-sync` (no args) | no | Usage error, exit 2 |
| `spell-sync ui` | yes | TUI |
| `spell-sync ui` | no | Controlled error, exit 2 |

Routing logic: `spell_sync/tui/routing.py` (`should_launch_tui`).

### CLI commands (11)

`config-check`, `doctor`, `init`, `lint`, `plan`, `pull`, `push`, `recover`, `status`, `ui`, `version`

CLI and TUI call the same `SpellSyncService` methods for setup, pull, push, recovery, status,
doctor, logs, and post-setup target settings.

## Screen map

### Setup wizard

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Welcome | `setup_welcome_screen.py` | Setup, Quit |
| Wordlist | `setup_welcome_screen.py` | Continue, Back |
| Targets | `setup_targets_screen.py` | Continue, Back, Refresh |
| Setup preview | `setup_welcome_screen.py` | Confirm, Back |
| Setup confirmation | `setup_confirm_screen.py` | Create project, Back |
| Setup operation | `operation_screen.py` | (worker) |
| Setup report | `report_screen.py` | Dashboard |

### Dashboard (sectioned)

| Section | Actions |
|---------|---------|
| Summary | Canonical wordlist path, word count, target counts, overall state, last operation |
| Primary | **Review and update** (guided flow); **Review recovery** when pending |
| Direct actions | Pull new words, Push wordlist |
| Manage | Targets |
| Support | Health (doctor), History (operation log) |
| Exit | Quit |

Hotkeys: `r` refresh, `s` status, `h` health. Status is not a dashboard button.

Blocking banners use `UserNotice` catalog copy for recovery, invalid config, and unreadable
wordlist. Pull, Push, and Review are disabled while recovery is pending.

Module: `dashboard.py`.

### Targets (post-setup)

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Target selection | `target_settings_screen.py` | Toggle targets, Refresh, Select available, Review changes, Back |
| Target review | `target_settings_screen.py` | Confirm update, Back |
| Target operation | `operation_screen.py` | (worker) |
| Target report | `report_screen.py` | Dashboard |

Config-only writes via `PreparedTargetSettingsUpdate`; stale fingerprint stops safely.

### Review and update (guided)

In-memory session on `TuiController` — not persisted as a history record.

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Review start | `review_update_screen.py` | Start review, Back |
| Pull review | `review_update_screen.py` | Pull words, Skip Pull, View additions, Back |
| Pull confirm | `pull_confirm_screen.py` | Confirm, Back |
| Pull operation | `operation_screen.py` | (worker; `on_complete` hand-off) |
| Pull complete | `review_update_screen.py` | Build push preview |
| Push review | `review_update_screen.py` | Push changes, Finish without Push, View removals, Back |
| Push confirm | `push_confirm_screen.py` | Type PUSH (removals), Run, Back |
| Push operation | `operation_screen.py` | (worker; `on_complete` hand-off) |
| Session report | `review_update_screen.py` | Dashboard |

Fresh `PushPreview` is always built after Pull or Skip Pull. Pull and Push remain separate
operations with existing confirm/execute paths.

### Direct Pull and Push

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Pull preview | `pull_screen.py` | Preview, Execute, Back |
| Pull confirm | `pull_confirm_screen.py` | Confirm, Back |
| Push preview | `preview_screen.py` | Pull/Push, Back |
| Push confirm | `push_confirm_screen.py` | Type PUSH (removals), Run, Back |
| Removals detail | `removals_screen.py` | Back |
| Operation | `operation_screen.py` | (worker) |
| Report | `report_screen.py` | Dashboard |

Reports use `format_operation_report_text` with planned vs actual rows and `UserNotice`
explanations for skipped targets and sources.

### Support screens

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Status | `status_screen.py` | Back |
| Health | `doctor_screen.py` | Back |
| History | `logs_screen.py` | Filters, Clear, Technical log, Back |
| Technical log | `logs_screen.py` | Back |
| Recovery | `recovery_screen.py` | Recover, Discard, Back |
| Recovery confirm | `recovery_confirm_screen.py` | Type RECOVER, Run, Back |

Navigation: keyboard (Tab, Enter, Escape), mouse clicks, visible focus styles in `app.tcss`.
Workers use `LoadTokenMixin` for stale-result suppression; screens cancel work on dismiss.

## Invariants

### Product model

- All user-facing directions refer to **application custom dictionaries**.
- Built-in application dictionaries are outside the Spell Sync model and are never read or
  modified.
- Central copy lives in `spell_sync/application/product_concepts.py` (UI-neutral).

### Safety

- Config loaded and validated before mutating operations (`ValidatedRuntime`, `config_blocks_mutating`).
- Corrupt or unsupported dictionaries are not overwritten.
- Operation lock (`.spell-sync.lock`) prevents parallel mutating commands.
- Preview and execution share one immutable plan — no silent replan after confirmation.
- Fingerprints checked at execution (`plan_fingerprint_conflict`).
- Removal confirmation requires typing `PUSH` when removals are present.
- Transaction snapshots + journal v2 before writes; rollback on failure.
- Recovery does not overwrite external changes; journal/snapshots preserved on incomplete rollback.
- Setup and target-settings writes touch project config only; external dictionaries are not
  modified during setup or target toggles.
- `--dry-run` never mutates files.
- `--json` emits exactly one JSON object on stdout.
- User words must not appear in technical logs or operation history.
- TUI never opens state files directly; reads go through `SpellSyncService`.
- Diagnostic paths come from configured platform roots only — never from TUI/CLI user input.
- History or logging failures never change the core operation outcome.
- Guided review session is in-memory only; history records Pull/Push/Targets executions individually.

## Setup wizard

Target toggles are UI controls only. Discovery defaults are a starting point; the wizard stores
exact selection on `TuiController` until confirmation.

If a target becomes corrupt after preview, execution uses the immutable `PreparedProjectSetup` from
preview — selected target IDs and rendered config bytes are not recomputed at execution time.

## Operation history and diagnostics

### Recorded operations

History records are appended after a completed mutating attempt for: Setup, Pull, Push, Targets
(target settings update), Recover, recovery cleanup, recovery discard.

Not recorded: status, preview/plan, doctor, discovery, refresh, cancel-before-execute, wizard
navigation, guided review session shell, opening the TUI.

### Stored fields

`OperationHistoryRecord` (schema v1): counts, operation kind, typed outcome, duration, warning
count, opaque identifiers. Never wordlist words, dictionary contents, secrets, or full absolute
user paths.

### Platform paths

| Platform | State directory | Technical log |
|----------|-----------------|---------------|
| macOS | `~/Library/Application Support/spell-sync/` | `~/Library/Logs/spell-sync/spell-sync.log` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/spell-sync/` | same state dir / `spell-sync.log` |
| Windows | `%LOCALAPPDATA%\spell-sync\` | `%LOCALAPPDATA%\spell-sync\logs\spell-sync.log` |

History file: `operation-history.jsonl` (max 500 records, JSON Lines, file lock).

Technical log: `RotatingFileHandler` — 1 MiB × 5 backups, UTF-8, redacted formatter.

### Failure behavior

History or logging failures never change the core operation outcome. Reports may add a
non-blocking warning. Errors go to the technical log only (no traceback in TUI).

## Testing

Headless Textual tests live in `tests/tui/`. Run:

```bash
python3.11 -m pytest tests/tui -q
scripts/ci.sh
```

Coverage policy: 100% line coverage on `spell_sync`, ≥96% branch coverage.
