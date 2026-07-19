# Spell Sync 0.2 UX implementation

## Goal

Local UX release `0.2.0`: post-setup Targets management, simpler Dashboard, guided
`Review and update`, clearer notices/reports. Preserve safety invariants. No large
architecture rewrite, no remote publish.

## Existing architecture

- Version: `0.1.0` (`pyproject.toml`)
- CLI commands: `config-check`, `doctor`, `init`, `lint`, `plan`, `pull`, `push`,
  `recover`, `status`, `ui`, `version` (`spell_sync/cli.py` `COMMANDS`)
- Shared facade: `SpellSyncService` (`spell_sync/application/service.py`)
- TUI entry: no-args TTY / `spell-sync ui` → `cmd_ui` → Textual app
- Dashboard actions today: Status, Preview, Doctor, Pull, Push, Recovery
  (conditional), Logs, Quit (`spell_sync/tui/screens/dashboard.py`)
- Config target schema: `[dictionaries]` boolean keys only
  (`editors`, `chrome`, `edge`, `brave`, `vivaldi`, `firefox`, `neovim`,
  `jetbrains`, `hunspell`, `obsidian`, `libreoffice`) — no `[targets].enabled`
- Target discovery DTO: `SetupTarget` / `SetupTargetDiscovery`
  (`spell_sync/project_setup/discovery.py`) fields include `identifier`,
  `display_name`, `path`, `detected`, `available`, `readable`, `supported`,
  `selectable`, `word_count`, `status`, `detail` (setup uses `enabled_by_default`)
- Config writer today: `render_project_config` → bytes in `PreparedProjectSetup` →
  `atomic_write` only during setup (`project_setup/render.py`, `execute.py`)
- No post-setup config mutation API
- Immutable previews: `PullPreview`, `PushPreview`, `RecoveryPreview`,
  `PreparedProjectSetup`, `PreparedPush`
- Operation report: `OperationReport` (`application/reports.py`)
- Recovery open path: Dashboard `action_open_recovery` → `RecoveryScreen` →
  `controller.inspect_recovery()`
- Setup selection path: TUI `SetupSelection` on controller → `SetupDraft` →
  `prepare_project_setup` → rendered TOML → `execute_project_setup`

## Safety invariants

- Strict config validation; effective wordlist defines project directory
- Pending recovery blocks new write operations
- Operation lock required for mutating operations
- Preview and execution share one immutable prepared plan
- Fingerprint checked before write; stale preview is not executed
- Push removal confirmation binds to exact plan
- Corrupt / unreadable / unsupported targets are not overwritten
- Running application checks are not bypassed
- Transaction snapshots before writes; journal kept on incomplete rollback
- Recovery does not overwrite external changes; successful recovery cleans artifacts
- TUI does not call low-level writers or CLI via subprocess
- CLI and TUI share application layer
- User words never stored in history or technical logs

## Product decisions

- Keep current TOML schema (`[dictionaries]` booleans)
- Reuse setup discovery/selection patterns for post-setup Targets
- Targets update writes config only (never dictionaries/wordlist/journal)
- Immutable `PreparedTargetSettingsUpdate` with rendered bytes + fingerprint
- Guided Review session is in-memory only (not a history record / transaction)
- Defer architecture items listed in task (CliOptions split, TargetAdapter, etc.)

## Current phase

Phase 4 — UserNotice / planned vs actual (complete)

## Completed phases

### Phase 0 — baseline and audit

- Production code unchanged for audit (docs hygiene only)
- Fixed pre-existing docs style failure: removed horizontal rules from
  `docs/TEST_REPORT_TEMPLATE.md` (blocked `scripts/check-docs-style.sh`)
- Created this working document
- Baseline green: ruff, mypy, `pytest tests/tui` (190), full `scripts/ci.sh`
  (1229 passed, 100% lines, 96.17% branches)

### Phase 1 — Targets management after setup

Application API on `SpellSyncService`:

- `load_target_settings(opts)` → `TargetSettingsSnapshot`
- `prepare_target_settings_update(opts, selected_target_ids)` →
  `PreparedTargetSettingsUpdate`
- `execute_target_settings_update(opts, prepared, confirmed_update_id=...)` →
  `TargetSettingsExecution`
- `build_target_settings_report(execution)` → `OperationReport`

Implementation:

- `spell_sync/project_setup/target_settings.py` — load, prepare, execute
- `spell_sync/project_setup/discovery.py` — `enabled` on `SetupTarget`,
  `enabled_dictionary_targets()`
- `spell_sync/project_setup/render.py` — preserve `[push]`, `[io]`, `[neovim]`
  when re-rendering post-setup
- `spell_sync/project_setup/selection.py` — `selection_from_enabled()`
- `spell_sync/application/service.py`, `builders.py`, `events.py` (`TARGETS`)
- `spell_sync/diagnostics/history_builder.py` — target settings history rows
- TUI: `target_settings_screen.py`, `controller.py`, `dashboard.py` (Targets
  button), `operation_screen.py`, `report_screen.py`

Safety:

- Config-only writes; dictionaries/wordlist/journal/snapshots untouched
- Immutable `PreparedTargetSettingsUpdate` with rendered bytes + fingerprint
- Stale fingerprint stops safely with user-facing message
- Corrupt/unreadable/unsupported/ambiguous targets not force-enabled
- Pending recovery blocks prepare/execute
- Operation lock during execute; TUI routes through `SpellSyncService` only

Tests:

- `tests/test_target_settings.py` (29 tests)
- `tests/tui/test_target_settings_screen.py` (6 tests)
- `tests/tui/test_target_settings_coverage.py` (18 tests)
- Architecture guards in `tests/tui/test_architecture.py`
- `tests/tui/test_dashboard.py` — Targets navigation

### Phase 2 — simplify Dashboard

Application data on `DashboardState`:

- `targets_ready`, `targets_needs_attention`, `targets_disabled`,
  `targets_unavailable`
- `last_operation_summary` (from most recent history record, no hashes)

Implementation:

- `spell_sync/application/builders.py` — application counts, last-operation
  summary helper, extended `build_dashboard_state`
- `spell_sync/application/service.py` — `load_dashboard` loads history tail
- `spell_sync/tui/screens/dashboard.py` — sectioned layout, blocking banners,
  primary `Review and update`, renamed Health/History, removed Preview button
- `spell_sync/tui/screens/review_update_screen.py` — Phase 3 placeholder stub

Dashboard layout:

- Summary: canonical wordlist path (with `~`), word count, application counts,
  overall state, last operation when history exists
- Primary: `Review and update` (stub screen; Phase 3 replaces flow)
- Direct actions: Pull new words, Push wordlist (opens preview as today)
- Manage: Targets
- Support: Health (doctor screen), History (logs screen)
- Recovery: `Review recovery` primary when pending; Pull/Push/Review disabled
- Blocking banners for recovery, invalid config, unreadable wordlist
- Status remains available via `s` hotkey (not a dashboard button)
- CLI `plan` unchanged

Tests:

- `tests/tui/test_dashboard.py` — ready/warning/blocked/recovery layouts,
  navigation, keyboard, 80×24, no duplicate Preview
- Updated navigation tests in `test_app.py`, `test_logs_screen.py`,
  `test_preview_screen.py`, `test_recovery_flow.py`, `test_status_screen.py`
- `tests/test_application_builders.py` — application counts and last-operation
  formatting

### Phase 3 — guided Review and update

Application model:

- `ReviewSession` / `ReviewSessionReport` (`spell_sync/application/review_session.py`)
- Controller-owned in-memory session on `TuiController` (not persisted, not a
  history record)

Flow:

- Dashboard → Review start → Pull review → optional Pull → Pull complete →
  fresh Push preview → optional Push → in-memory session report
- Pull and Push remain separate operations with existing confirm/execute paths
- Fresh `PushPreview` always built after Pull or Skip Pull (never reused)

Implementation:

- `spell_sync/tui/screens/review_update_screen.py` — start, pull review, pull
  complete, push preview, session report screens
- `spell_sync/tui/controller.py` — `begin_review_session`, `prepare_review_pull`,
  `prepare_review_push`, session record helpers
- `spell_sync/tui/screens/operation_screen.py` — optional `on_complete` callback
  for review hand-off (skips standalone report when set)
- `spell_sync/tui/screens/dashboard.py` — primary action opens guided flow

Safety:

- Pull/Push confirmation binds to exact preview plan id
- Stale preview blocked via existing confirm screens
- Recovery / failed outcomes end session with recovery note
- History records only for executed Pull/Push (not the review session)

Tests:

- `tests/test_review_workflow.py` — session report helpers
- `tests/tui/test_review_workflow.py` — end-to-end guided flow
- `tests/tui/test_review_coverage.py` — screen edge paths
- Architecture guards in `tests/tui/test_architecture.py`

### Phase 4 — UserNotice / planned vs actual

Application model:

- `UserNotice` / `NoticeSeverity` / `NOTICE_CATALOG` (`spell_sync/application/user_notices.py`)
- Planned vs actual helpers (`spell_sync/application/operation_explanations.py`)
- `DashboardIssue` kept; mapped to `UserNotice` for display via `dashboard_issue_to_notice`

Catalog:

- Single text source for 13 reason codes: title, explanation, suggested action
- Technical detail: reason code + target id only (no paths, hashes, or user words)

Reports:

- Push: Planned/Actual target rows with per-target status (Updated, Skipped: …)
- Pull: Planned vs actual additions and skipped-source explanations
- Allowed metadata: preview created time, plan verified, recovery snapshots cleaned
- `PushExecution.push_preview` links execution back to the immutable preview

Screens updated (NEW/main only):

- Dashboard blocking banners and issue lines via `UserNotice`
- Targets load-error banner via catalog
- Recovery blocker copy via catalog
- Push/Pull report screen via `format_operation_report_text`
- Review session inherits updated operation reports

Tests:

- `tests/test_user_notices.py` — catalog, mapping, planned/actual, sensitivity guards
- Updated TUI expectations in dashboard, push flow, phase4 coverage

## Last validation

```bash
python3.11 -m ruff check spell_sync tests          # pass
python3.11 -m ruff format --check spell_sync tests # pass
python3.11 -m mypy spell_sync                      # pass
python3.11 -m pytest tests/test_user_notices.py tests/tui -q  # pass
bash scripts/ci.sh                                 # EXIT 0
coverage policy: 100% lines, 96%+ branches
```

## Remaining work

### Later phases

- Phase 5: docs + version `0.2.0`

## Deferred work

- Full removal of `CliOptions` from application layer
- Split `SpellSyncService` into multiple services
- TargetAdapter architecture
- Remove global active settings
- Config schema `[targets].enabled`
- Rewrite all builders / replace transaction engine
- Native GUI, tray, daemon, watcher, auto updater, telemetry, plugins
- Automatic Pull/Push/Git/background sync
- Changelog, tags, PyPI publish, remote changes
