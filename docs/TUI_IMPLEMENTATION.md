# TUI implementation

## Current architecture

```text
spell_sync/cli.py          argparse, COMMANDS dispatch, entry_point
    ↓
CliOptions                 frozen dataclass from argparse namespace
    ↓
command modules            commands.py, plan_cmd.py, doctor.py, recover_cmd.py, …
    ↓
command_helpers.py         sync_run_for, mutating_command_scope, JSON/human exits
    ↓
validated_runtime.py       ValidatedRuntime (config + journal under lock)
project.py                 ProjectContext (wordlist → project_dir, config_paths)
sync_context.py            RuntimeContext, runtime_context_for()
    ↓
sync_run.py                SyncRun — pull, push, status, plan orchestration
push_prepared.py           PreparedPush (immutable), prepare_push(), execute_prepared_push()
push_setup.py / push_plan.py / push_render.py / push_transaction.py / push_journal.py
health/                    DoctorReport, build_doctor_report()
```

### CLI entry path

| Item | Location |
|------|----------|
| Console script | `[project.scripts] spell-sync = "spell_sync.cli:entry_point"` |
| Module main | `spell_sync/__main__.py` → `cli.main()` |
| Parser | `cli._build_parser()` — 10 subcommands |
| Dispatch | `cli.main()` → `COMMANDS[command](opts)` |

### Command execution map

| Operation | Entry | Core path |
|-----------|-------|-----------|
| **status** | `commands.cmd_status` | `sync_run_for` → `run.check_wordlist` → `run.status_diffs` |
| **plan** | `plan_cmd.cmd_plan` | `sync_run_for` → `run.plan_push` (dry-run transaction) or `list_removals` with `--removals` |
| **pull prep/exec** | `commands.cmd_pull` | `mutating_command_scope` → `run.pull_into_wordlist()` or `run.pull_add_from()` |
| **push prep** | `commands._cmd_push_locked` | `run.prepare_push_operation()` → `prepare_push(ctx, words)` → `PreparedPush` |
| **push exec** | `commands._cmd_push_locked` | `run.push_from_wordlist(prepared=prepared)` → `execute_prepared_push(prepared, dry_run=False)` |
| **push dry-run** | same | `run._run_push_transaction(dry_run=True, prepared=prepared)` |
| **doctor** | `doctor.cmd_doctor` | `sync_run_for` → `build_doctor_report(run, …)` |
| **recover** | `recover_cmd.cmd_recover` | `mutating_command_scope(allow_unfinished_journal=True)` → `recover_from_journal` |

### Existing result types (reuse for facade)

| Type | Module | Role |
|------|--------|------|
| `CliOptions` | `cli_options.py` | CLI/TUI options bag |
| `ValidatedRuntime` | `validated_runtime.py` | Config + journal + `RuntimeContext` |
| `ProjectContext` | `project.py` | Wordlist-relative project paths |
| `RuntimeContext` | `sync_context.py` | Wordlist, config, discovered dictionaries |
| `PreparedPush` | `push_prepared.py` | Immutable push plan + rendered payloads |
| `PushPlan` / `PlannedTarget` | `push_plan.py` | Plan structure |
| `PushResult` | `sync_models.py` | written / skipped dictionaries |
| `DictionaryDiff` | `sync_models.py` | Status/plan per-target diff |
| `DoctorReport` | `health/types.py` | Doctor checks and actions |
| `RecoverResult` | `push_journal.py` | Recovery outcome |
| `JournalLoadResult` | `push_journal.py` | Pending/corrupt journal state |
| `ConfigLoadResult` | `settings.py` | Config validation diagnostics |
| `ExitCode` | `exit_codes.py` | Typed exit reasons |

There is **no** existing `application/` package or shared service layer. CLI modules call `SyncRun` and helpers directly.

### No-argument behavior (baseline)

- Empty argv → `_parse_args([])` returns `Namespace(command="status", …)` → **`status` runs**.
- `--help` / `-h` → prints help, exit 0.
- Unknown command → exit `UNKNOWN_COMMAND` (2).
- **No TUI** today; non-TTY empty argv still runs `status` (exit 0).

### Baseline metrics (2026-07-18)

| Metric | Value |
|--------|-------|
| CLI subcommands | 10: `status`, `pull`, `push`, `plan`, `config-check`, `lint`, `recover`, `init`, `doctor`, `version` |
| Python requirement | `>=3.11` |
| Runtime dependencies | none (`dependencies = []`) |
| Console entry | `spell_sync.cli:entry_point` |
| Tests | 741 passed, 59 subtests |
| Workflow | `scripts/ci.sh` (no `uv.lock` in repo) |

### Baseline validation (Phase 0)

```bash
cd ~/code/spell-words/spell-sync
python3.11 -m ruff check spell_sync tests          # All checks passed
python3.11 -m ruff format --check spell_sync tests   # 98 files already formatted
python3.11 -m mypy spell_sync                      # Success: no issues in 51 files
python3.11 -m pytest tests -q                        # 741 passed, 59 subtests
```

Note: project gate is `scripts/ci.sh` (coverage, wheel smoke, gui smoke). Full CI not re-run in Phase 0 (production code unchanged).

## Invariants

TUI must preserve existing safety properties:

- Config loaded and validated before mutating operations (`ValidatedRuntime`, `config_blocks_mutating`).
- Effective wordlist and project directory from `ProjectContext.build` / `resolve_wordlist_path`.
- Invalid config blocks mutating commands.
- Corrupt or unsupported dictionaries are not overwritten (`ReadStatus`, push plan skips).
- Operation lock (`.spell-sync.lock`) prevents parallel mutating commands.
- Preview and execution share one `PreparedPush` — no silent replan after confirmation.
- Fingerprints checked at execution (`plan_fingerprint_conflict`, `fingerprint_conflict`).
- Removal limits enforced via `confirm_push_removals` / `max_removals_in_plan`.
- Transaction snapshots + journal v2 before writes; rollback on failure.
- Recovery does not overwrite external changes; journal/snapshots preserved on incomplete rollback.
- `--dry-run` never mutates files.
- `--json` emits exactly one JSON object on stdout (via `log.quiet`).
- User words must not appear in technical logs or operation history.

## Decisions

| Decision | Choice |
|----------|--------|
| UI framework | Textual (`textual>=8.2.8,<9`) — not yet added |
| Application layer | New `spell_sync/application/` facade wrapping existing `SyncRun` / helpers |
| CLI compatibility | Keep all existing subcommands; add `ui`; no-arg TTY → TUI (Phase 2+) |
| Options type | Extend or mirror `CliOptions`; avoid duplicate domain models |
| Events | `EventSink` protocol in application layer; core stays Textual-free |
| Phase 1 CLI migration | Start with `status` + `push` only |

## Phases

- [x] Phase 0 — baseline
- [x] Phase 1 — application facade
- [x] Phase 2 — TUI shell
- [ ] Phase 3 — status and plan
- [ ] Phase 4 — pull and push
- [ ] Phase 5 — first-run wizard
- [ ] Phase 6 — reports and logs
- [ ] Phase 7 — packaging and documentation
- [ ] Phase 8 — final validation

## Current phase

Phase 2 — TUI shell (complete). Next: Phase 3 — status and plan screens polish.

## Last validation

```bash
cd ~/code/spell-words/spell-sync
python3.11 -m pytest tests/tui -q          # 35 passed
scripts/ci.sh                               # exit 0 — 789 passed, 100% line coverage
cd ~/code/spell-sync-dev && scripts/health.sh  # 0 fail
```

### Phase 2 deliverables

| Component | Path |
|-----------|------|
| Dependency | `pyproject.toml` — `textual>=8.2.8,<9` |
| Routing | `spell_sync/tui/routing.py` — `should_launch_tui()` |
| Launch | `spell_sync/tui/launch.py` — `cmd_ui` |
| App shell | `spell_sync/tui/app.py`, `app.tcss`, `controller.py` |
| Screens | `spell_sync/tui/screens/` — dashboard, status, preview |
| CLI | `spell_sync/cli.py` — `ui` subcommand; no-arg TTY → TUI; non-TTY → exit 2 |
| Service | `load_dashboard`, `load_push_preview` on `SpellSyncService` |
| Tests | `tests/tui/` — 35 headless tests (routing, app, launch) |

Working actions: Status, Preview, Quit, Refresh, Escape-back. Disabled (Phase 4+): Pull, Push, Doctor, Recovery, Logs.

### Phase 1 deliverables

| Component | Path |
|-----------|------|
| Event types | `spell_sync/application/events.py` |
| Status/push reports | `spell_sync/application/reports.py` |
| Facade | `spell_sync/application/service.py` — `SpellSyncService` |
| CLI wiring | `commands.cmd_status`, `commands._cmd_push_locked` |
| Tests | `tests/test_application_service.py` |

`SpellSyncService` methods: `load_status`, `prepare_push`, `execute_push`, `run_push`. Push execution reuses the same `PreparedPush` object and checks fingerprints before calling `run.push_from_wordlist(prepared=...)`.

## Setup wizard target selection (Phase 6.1)

Setup target toggles are UI controls only. Discovery defaults are a starting point; the
wizard stores exact selection in `SetupSelection` on `TuiController` until confirmation.

### Post-preview semantics

Setup writes only project files (`wordlist.txt`, `spell-sync.toml`, whitelist). External
application dictionaries are never modified during discovery, toggle, refresh, preview, or
project creation.

If a target becomes corrupt or its discovery path changes after preview:

- `execute_project_setup()` uses the immutable `PreparedProjectSetup` from preview
- Selected target IDs and rendered config bytes are not recomputed at execution time
- Config records enabled flags from the prepared selection only
- Dashboard after setup may show warnings for targets that later become unreadable/corrupt

This is covered by `tests/test_setup_target_selection.py`.
