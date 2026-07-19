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
command_helpers / SyncRun      existing pull, push, recover, status core
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
doctor, and logs.

## Screen map

| Screen | Module | Primary actions |
|--------|--------|-----------------|
| Welcome | `setup_welcome_screen.py` | Setup, Quit |
| Wordlist | `setup_welcome_screen.py` | Continue, Back |
| Targets | `setup_targets_screen.py` | Continue, Back, Refresh |
| Setup preview | `setup_welcome_screen.py` | Confirm, Back |
| Setup confirmation | `setup_confirm_screen.py` | Create project, Back |
| Setup operation | `operation_screen.py` | (worker) |
| Setup report | `report_screen.py` | Dashboard |
| Dashboard | `dashboard.py` | Pull, Push, Status, Doctor, Recovery, Logs, Quit |
| Status | `status_screen.py` | Back |
| Preview | `preview_screen.py` | Pull/Push, Back |
| Pull | `pull_screen.py` | Preview, Execute, Back |
| Push confirmation | `push_confirm_screen.py` | Type PUSH (removals), Run, Back |
| Operation | `operation_screen.py` | (worker) |
| Report | `report_screen.py` | Dashboard |
| Doctor | `doctor_screen.py` | Back |
| Recovery | `recovery_screen.py` | Recover, Discard, Back |
| Logs | `logs_screen.py` | Filters, Clear, Technical log, Back |
| Technical log | `logs_screen.py` | Back |

Navigation: keyboard (Tab, Enter, Escape), mouse clicks, visible focus styles in `app.tcss`.
Workers use `LoadTokenMixin` for stale-result suppression; screens cancel work on dismiss.

## Invariants

- Config loaded and validated before mutating operations (`ValidatedRuntime`, `config_blocks_mutating`).
- Invalid config blocks mutating commands.
- Corrupt or unsupported dictionaries are not overwritten.
- Operation lock (`.spell-sync.lock`) prevents parallel mutating commands.
- Preview and execution share one immutable plan — no silent replan after confirmation.
- Fingerprints checked at execution (`plan_fingerprint_conflict`).
- Removal confirmation requires typing `PUSH` when removals are present.
- Transaction snapshots + journal v2 before writes; rollback on failure.
- Recovery does not overwrite external changes; journal/snapshots preserved on incomplete rollback.
- Setup writes only project files; external dictionaries are never modified during setup.
- `--dry-run` never mutates files.
- `--json` emits exactly one JSON object on stdout.
- User words must not appear in technical logs or operation history.
- TUI never opens state files directly; reads go through `SpellSyncService`.
- Diagnostic paths come from configured platform roots only — never from TUI/CLI user input.
- History or logging failures never change the core operation outcome.

## Setup wizard

Target toggles are UI controls only. Discovery defaults are a starting point; the wizard stores
exact selection on `TuiController` until confirmation.

If a target becomes corrupt after preview, execution uses the immutable `PreparedProjectSetup` from
preview — selected target IDs and rendered config bytes are not recomputed at execution time.

## Operation history and diagnostics

### Recorded operations

History records are appended after a completed mutating attempt for: Setup, Pull, Push, Recover,
recovery cleanup, recovery discard.

Not recorded: status, preview/plan, doctor, discovery, refresh, cancel-before-execute, wizard
navigation, opening the TUI.

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
