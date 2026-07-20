# Spell Sync 0.3 architecture implementation

## Goal

Prepare architectural release 0.3.0: typed application requests, explicit runtime
context, thin facade with focused services, structured technical events, current
documentation, and architecture validation guards.

Remove obsolete private maintainer export workflow (completed in spell-sync-dev).

## Verified baseline

| Repository | HEAD | Clean |
|------------|------|-------|
| spell-sync | `c9b46bc` docs: add platform validation readiness report | yes |
| spell-sync-dev | `3dcf017` chore: remove obsolete private export tooling | yes |
| spell-words | `c7ffed5` chore: add data repository agent guide | yes |

Public version: `0.2.1` (`pyproject.toml`).

## Current dependency graph

```text
CLI (cli.py, commands.py, *_cmd.py)
  → CliOptions, command_helpers, sync_run, sync_context
  → SpellSyncService (application/service.py)
  → builders.py, sync_run, push_*, pull, project_setup, diagnostics

TUI (tui/controller.py, screens/)
  → CliOptions, SpellSyncService protocol
  → workers → service methods

Settings (settings.py)
  → ContextVar _active_settings, module cache
  → bind_active_settings() from sync_context, validated_runtime, dictionaries

Validated runtime (command_helpers.py)
  → ContextVar _active_validated
  → mutating_command_scope sets/resets
```

## Global state inventory

| Location | Symbol | Kind |
|----------|--------|------|
| `settings.py:125-130` | `_settings_cache`, `_settings_cache_key`, `_active_settings` | module cache + ContextVar |
| `command_helpers.py:26-29` | `_active_validated` | ContextVar |
| `technical_logging.py:14-16` | `_CONFIGURED`, `_HANDLER`, `_CONFIGURED_LOG` | module logging state |
| `dictionaries.py:305` | `bind_active_settings()` call | implicit settings scope |

No module-level mutable state in `runtime.py`, `sync_context.py` (builders only),
`validated_runtime.py` (frozen dataclass factory).

## Service responsibility inventory

### SpellSyncService (~1284 lines)

Inspection: status, status_detail, dashboard, push_preview, doctor.

Synchronization: prepare/execute pull, prepare/execute push, run_push, push execution
helpers, reports.

Recovery: inspect, execute, cleanup, discard.

Setup: inspect, discover, prepare, execute, validate wordlist, reports.

Target settings: load, prepare update, execute update, report.

Diagnostics: history, technical log tail, support report delegation.

Internal: `_finalize_report`, event emit helper.

### builders.py (~1183 lines)

Presentation builders for dashboard, status, pull/push/recovery/setup/targets,
doctor, previews.

### TuiController (~726 lines)

Screen routing, service protocol mirroring CliOptions-based service API, session
state for review/target settings/recovery flows.

## Logging gap analysis

Today:

- `OperationEvent` uses free-form `stage: str`; sink is UI-only (`events.py`).
- File technical log (`technical_logging.py`) uses stdlib logging + safe formatter;
  few warning lines on setup/history failure.
- No structured JSON Lines lifecycle per operation ID.
- History is compact user summary via `history_store`.

Gaps: no enum stages, no operation_id continuity in technical log, no per-target
structured events, legacy plain-text only.

## Safety invariants

See `docs/RECOVERY.md`, `AGENTS.md`, `.cursor/rules/project-safety.mdc`. All
mutation paths must preserve preview/execute binding, lock, journal, Recovery
blocking, and privacy rules.

## Migration order

1. ~~Remove obsolete private maintainer export tooling (spell-sync-dev)~~ done
2. Typed application requests + CLI adapter
3. Explicit runtime settings + RuntimeResolver; remove ContextVars
4. Split application services + presenters; thin facade
5. Structured technical events
6. Architecture validator + PROJECT_MAP
7. Documentation reorganization + ADRs
8. Agent config refresh
9. Version 0.3.0

## Current phase

Phase 2E complete. Phase 3 is next and has not started.

[architecture-status:start]
current: phase-3
phase-1: complete
phase-2: complete
phase-2b: complete
phase-2c: complete
phase-2d: complete
phase-2e: complete
phase-3: not-started
[architecture-status:end]

## Phase 2B: complete application boundary

### CLI bypass inventory (resolved)

| Command | Before | After |
|---------|--------|-------|
| status | service | service |
| pull | CLI `SyncRun` | `prepare_pull` / `execute_pull` |
| push | CLI `SyncRun` + `prepare_push(run)` | `load_push_preview` / `execute_push_preview` |
| recover | journal internals in CLI | `inspect_recovery` + typed execution |
| doctor | CLI `sync_run_for` | `load_doctor_report` / `load_doctor_targets` |
| plan | CLI `sync_run_for` | `load_push_plan` / `execute_push_dry_run` |
| init | service (draft in CLI) | service (unchanged draft assembly) |
| config-check | CLI settings utility | CLI utility (documented exception) |
| lint | CLI lint core | CLI utility (documented exception) |
| support-report | typed request | service/report boundary |
| ui | adapter | adapter |
| version | presentation | presentation |

### Dead requests and mappers (resolved)

Removed unused `ConfigCheckRequest`, `LintRequest`, `config_check_request()`, `lint_request()`.
Removed unused `OperationSource`.

### Reverse dependency inventory (resolved)

Core/project modules no longer import `spell_sync.application`. Resolution lives in
`application/project_resolution.py`.

### Required final service entrypoints

Public: `prepare_pull`, `execute_pull`, `load_push_preview`, `execute_push_preview`,
`execute_push_dry_run`, `inspect_recovery`, `execute_recovery*`, `load_doctor_report`,
`load_doctor_targets`, `load_push_plan`, `load_push_removals`.

Private: `_prepare_push_for_run`, `_execute_push_for_run`, `_run_push_for_run`.

Push strict resolution: `effective_push_strict()` in `project_resolution.py` (implicit
settings until Phase 3).

### Compatibility contracts

- CLI preflight (`mutating_command_scope`) preserved for JSON lock/config/journal exits
- Service reuses active validated context when CLI scope is open
- JSON schemas and exit codes unchanged

## Phase 2: typed request migration

See `docs/decisions/0001-typed-application-requests.md`.

### CliOptions field classification

| Field | Category |
|-------|----------|
| `wordlist` | Project selection |
| `add_from` | Operation semantics (Pull) |
| `strict` | Operation semantics (Push CLI override → `strict_override`) |
| `fix`, `strict` (lint) | Operation semantics (Lint) |
| `verbose` | Presentation (status diff detail via `include_word_diffs` mapping) |
| `dry_run`, `yes` | CLI transport / confirmation flow |
| `json_output` | Presentation only |
| `review_removals`, `plan_removals`, `health_check`, `show_targets` | CLI transport (command routing) |
| `discard_corrupt_journal` | CLI transport (recover flags) |
| `support_report_format`, `support_report_output` | Presentation only (export boundary) |

### Target request types

`ProjectRef`, `StatusRequest`, `DoctorRequest`, `PullRequest`, `PushRequest`,
`RecoveryRequest`, `SetupRequest`, `TargetSettingsRequest`,
`PrepareTargetSettingsUpdateRequest`, `SupportReportRequest`.

`config-check` and `lint` remain CLI-level utilities (no request types).

### Migration order

1. Add `application/requests.py`
2. Add `cli_request_adapter.py` with shared `project_ref()`
3. Migrate `SpellSyncService` to typed requests (single contract)
4. Migrate CLI commands (adapter → service → renderer)
5. Migrate TUI controller (direct request builders)
6. Remove `CliOptions` from application/TUI; add architecture guards

### Compatibility contracts

- CLI command names, arguments, defaults, exit codes unchanged
- JSON schemas and field ordering unchanged
- TUI navigation and copy unchanged
- Confirmation IDs remain separate execution arguments
- `CliOptions` retained as CLI parser DTO only

Summary:

- `CliOptions` is CLI parser DTO only; application layer uses `application/requests.py`
- `cli_request_adapter.py` is the sole production mapper from CLI DTO to requests
- TUI builds requests directly; presentation flags remain in CLI

## Completed phases

- Phase 0: baseline audit, this document
- Phase 1 (spell-sync-dev): removed obsolete private export and review-bundle tooling
- Phase 2: typed application requests + CLI adapter
- Phase 2B: pure request DTOs, service-only CLI mutations, dependency direction

## Last validation

```text
Phase 2B: pytest 1559+ passed; scripts/ci.sh green; 100% line coverage (2026-07-20)
```

## Remaining work

Phases 3–10 on public spell-sync repository (see migration order).

## Deferred work

- TUI flow split (`tui/flows/`) — only if controller refactor warrants it
- Developer stderr traceback mode — only if existing verbose path insufficient
