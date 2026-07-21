# Spell Sync 0.3 architecture implementation

## Goal

Prepare architectural release 0.3.0: typed application requests, explicit runtime
context, thin facade with focused services, structured technical events, current
documentation, and architecture validation guards.

Remove obsolete private maintainer export workflow (completed in spell-sync-dev).

## Current phase

Phase 5: structured technical events and diagnostics — **in progress** (implementation
finalized; **awaiting owner approval**). Phase 4 (focused application services and thin facade)
is **complete** and owner-approved.

[architecture-status:start]
current: phase-5
phase-1: complete
phase-2: complete
phase-2b: complete
phase-2c: complete
phase-2d: complete
phase-2e: complete
phase-3: complete
phase-4: complete
phase-5: awaiting-approval
[architecture-status:end]

## Verified baseline

| Repository | HEAD | Clean |
|------------|------|-------|
| spell-sync | `9bbdccc` docs: complete phase 4 and open phase 5 | no (Phase 5 WIP) |
| spell-sync-dev | `7bb8ecf` test: cover snapshot git timeout | yes |
| spell-words | `3e5bc29` docs: align maintainer agent guide with snapshot contract | yes |

Public version: `0.2.1` (`pyproject.toml`).

Phase 4 final CI evidence: `0a69064`, run `20260721T133915.258179Z`, `finalEvidence=true`.

Phase 5 final CI evidence: **pending** — run full `scripts/ci.sh` on committed clean HEAD after
owner approval.

## Current dependency graph

```text
CLI (cli.py, commands.py, *_cmd.py)
  → cli_request_adapter → typed application requests
  → SpellSyncService (application/service.py)
  → RuntimeResolver (application/runtime_resolver.py)
  → private _runtime_factory
  → ResolvedRuntime (config + journal + RuntimeIdentity)
  → RuntimeContext (wordlist, RuntimeSettings, dictionaries, strict_push)
  → sync_run / push_* / pull / project_setup / diagnostics (core)

TUI (tui/controller.py, screens/)
  → typed requests + SpellSyncService protocol
  → workers → same application path as CLI (no subprocess CLI, no direct core writers)

Settings (settings.py)
  → load_config_result per resolve (no module settings cache)
  → RuntimeSettings on RuntimeContext

Mutation lifecycle (Pull/Push/Recovery/target settings)
  confirmed preview (+ RuntimeIdentity at preview time)
  → operation lock
  → fresh config / settings / targets / journal resolution under lock
  → fresh RuntimeIdentity
  → comparison with preview identity (mismatch → STOPPED_SAFELY, no replan)
  → target fingerprint validation
  → transaction / journal / write
```

Runtime resolution invariants:

- Application facade owns runtime resolution; CLI and TUI do not construct runtime independently.
- `_runtime_factory` is private to resolution paths.
- No production `ContextVar` for settings or validated runtime.
- No module-level config cache.
- No hidden mutation runtime reused from preview time; execution resolves fresh state under lock.
- Changed runtime after preview blocks execution; no automatic replanning.

## Global state inventory

| Location | Symbol | Kind |
|----------|--------|------|
| `technical_logging.py` | `_CONFIGURED`, `_HANDLER`, `_CONFIGURED_LOG` | module logging bootstrap |

Removed in Phase 3 (must not reappear):

- `_settings_cache`, `_settings_cache_key` (settings module cache)
- `ContextVar` runtime scope for settings or validated runtime
- bound mutation runtime reuse across preview and execution
- stale preview runtime carried into execution

No production `ContextVar` for settings or validated runtime.
No module-level config cache in `settings.py`.
No hidden mutation runtime; fresh resolution under the operation lock via
`mutation_scope_for` / `RuntimeResolver.mutation_scope`.
`ResolvedRuntime` is the canonical resolved bundle; `ValidatedRuntime` remains a
compatibility alias only where legacy naming persists in tests or docs migration.

## Service responsibility inventory

### SpellSyncService (thin facade)

Delegates to focused services under `spell_sync/application/services/`:

| Service | Responsibility |
|---------|----------------|
| `DiagnosticsService` | History, technical log, support report, report finalization |
| `InspectionService` | Status, dashboard, doctor |
| `SyncService` | Pull/Push preview and execution |
| `RecoveryService` | Recovery preview and execution |
| `SetupService` | Project setup / init |
| `TargetSettingsService` | Target settings load and update |

Facade wiring: `ApplicationContext` shares `RuntimeResolver`, history store, and state paths.
See `docs/PROJECT_MAP.md` and ADR `docs/decisions/0003-focused-application-services.md`.

### builders.py (~1183 lines)

Presentation builders for dashboard, status, pull/push/recovery/setup/targets,
doctor, previews.

### TuiController (~726 lines)

Screen routing, service protocol mirroring CliOptions-based service API, session
state for review/target settings/recovery flows.

## Logging gap analysis

Resolved in Phase 5:

- ~~Free-form `OperationEvent.stage: str`~~ → typed `EventId` enum and `TechnicalEvent`
  dataclass (`application/events.py`).
- ~~UI-only event sink with duplicated messages~~ → `EventEmitter` splits technical file log
  and `PresentedEvent` via `event_presenter.py`; CLI/TUI receive presentation only.
- ~~Ad-hoc warning lines only~~ → JSON Lines per event with `schemaVersion: 1`
  (`diagnostics/technical_event_log.py`).
- ~~No operation continuity in technical log~~ → `correlationId` binds preview plan IDs,
  setup/update identifiers, and history record IDs on diagnostic failures.
- ~~No per-target structured metadata~~ → optional `targetId` on target-scoped events.
- ~~Plain-text-only tail display~~ → structured lines parsed for display; legacy lines fall
  back to `sanitize_log_message`.

Unchanged:

- Operation history remains compact user summaries via `history_store` (not a full event stream).
- Support report exposes redacted summaries and privacy manifest; no raw event payloads.
- Logging failure is fail-open and never blocks mutation paths.

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

## Phase 3 — Explicit runtime (complete)

### Goal

Replace implicit ContextVar-based settings and validated runtime with explicit resolution
through `RuntimeResolver`, runtime identity binding for preview/execution consistency,
and commit-bound final CI evidence.

### Scope (delivered)

- `spell_sync/application/runtime_resolver.py`, `application/_runtime_factory.py`
- `spell_sync/runtime_identity.py`, `spell_sync/resolved_runtime.py`
- `spell_sync/settings.py`, `spell_sync/sync_context.py`, `spell_sync/application/mutation_scope.py`
- `spell_sync/application/service.py`, `spell_sync/push_prepared.py`, `spell_sync/application/builders.py`
- Test selection infrastructure (`tests/test-impact.toml`, `scripts/test_selection/`, focused runners)
- Architecture tests, ADR, CI clean-tree and evidence gates

### Required outcomes (delivered)

- No production `ContextVar` for settings or validated runtime
- No module-level config cache
- `RuntimeResolver` resolves `ProjectRef` → `ResolvedRuntime` explicitly
- Fresh mutation resolution under the operation lock; no hidden reuse of preview runtime
- `RuntimeIdentity` stored at preview; execution compares fresh identity under lock
- Runtime or fingerprint mismatch stops safely; no automatic replanning
- CLI JSON, exit codes, and Pull/Push semantics unchanged
- Final CI evidence binds to committed clean HEAD

### Safety contracts (preserved)

- Operation lock, journal, Recovery, preview/execute binding unchanged
- Target fingerprint validation after identity match
- Privacy and mutation invariants unchanged

### Phase-specific validation (passed)

- `tests/test_explicit_runtime.py`, `tests/test_runtime_identity.py`
- `tests/test_runtime_architecture.py`, Pull/Push/Recovery safety suites
- Full final CI on `1ba73ba` with `finalEvidence=true`
- ADR `docs/decisions/0002-explicit-runtime.md` accepted

### Completion criteria (met)

- Architecture and runtime identity tests pass; full CI green on accepted HEAD
- Owner approval recorded; tracker status `complete`
- Phase 4 remains `not-started`

## Phase 4 — Focused application services and thin facade

**Status:** complete

### Preflight maintenance (complete)

1. **NUL-safe untracked digest** — `_untracked_paths()` uses `git ls-files -z`; regression
   test in `tests/test_tree_digest.py`.
2. **Snapshot Git timeout** — spell-sync-dev `_git_command()` uses
   `GIT_SUBPROCESS_TIMEOUT_SECONDS`.

### Delivered

- `spell_sync/application/services/` package with six focused services + shared context
- Thin `SpellSyncService` facade (delegation only)
- ADR `docs/decisions/0003-focused-application-services.md`
- `docs/PROJECT_MAP.md`
- Architecture tests in `tests/test_application_services.py`

### Goal

Split the monolithic `SpellSyncService` and presentation builders into focused UI-neutral
services while keeping one compatible application facade for CLI and TUI.

### Scope

Minimum:

```text
spell_sync/application/service.py
spell_sync/application/builders.py
spell_sync/application/reports.py
spell_sync/application/runtime_resolver.py
spell_sync/application/*
spell_sync/tui/controller.py
application service protocols
architecture tests
project map
ADR
```

### Required outcomes

- `SpellSyncService` becomes a thin compatibility facade.
- Focused services by responsibility:
  - inspection / status / doctor;
  - Pull/Push synchronization;
  - Recovery;
  - setup / init;
  - target settings;
  - diagnostics / history / support report.
- Presentation builders separated from mutation orchestration.
- CLI and TUI use one application path.
- Focused services do not import CLI/TUI modules.
- Core does not import the application layer.
- Runtime resolution remains through `RuntimeResolver`.
- Mutation services receive fresh scoped runtime.
- No parallel execution paths.
- Legacy facade methods either delegate to one canonical service path or are removed after
  all consumers migrate.
- No unused service abstractions remain.

### Safety contracts

Unchanged:

- Pull union semantics;
- Push replication / filter semantics;
- built-in dictionary exclusion;
- operation lock;
- journal and Recovery blocker;
- snapshots / backups / rollback;
- exact confirmation ID;
- RuntimeIdentity preview/execution binding;
- target fingerprints;
- no automatic replan;
- privacy contracts;
- CLI JSON and exit codes.

### Deferred

Do not start:

- structured technical events (Phase 5);
- version `0.3.0`;
- CLI redesign;
- TUI redesign;
- release / tag / publication;
- product semantic changes.

### Phase-specific validation

Minimum:

```text
architecture dependency tests
application facade delegation tests
focused service tests
runtime identity tests
Pull/Push transaction safety
Recovery safety
CLI/TUI equivalence
TUI architecture tests
full final CI
installed-wheel smoke
```

### Completion criteria (met)

- Facade substantially thinner; responsibilities have a single owner.
- No CLI/TUI bypasses.
- Mutation invariants preserved.
- Architecture guards forbid reverse dependencies.
- Legacy parallel helpers removed.
- Docs, ADR, and project map current.
- Final CI on committed clean HEAD.
- Owner approval recorded; tracker status `complete`.

### Owner acceptance (recorded)

- focused application services created under `spell_sync/application/services/`;
- `SpellSyncService` is a thin delegation facade;
- `ApplicationContext` is frozen;
- CLI and TUI use canonical application paths;
- runtime resolution remains through `RuntimeResolver`;
- mutation safety and `RuntimeIdentity` preserved;
- private legacy facade orchestration removed;
- final CI evidence bound to committed HEAD `0a69064`;
- coverage correction commit `0a69064` accepted;
- Phase 5 was not started before approval.

## Phase 5 — Structured technical events and diagnostics

**Status:** awaiting approval

### Goal

Replace scattered free-form stage strings and ad-hoc technical logging with typed
structured technical events while keeping presentation-neutral application and core
boundaries.

### Delivered

- `spell_sync/application/events.py` — `EventId`, `TechnicalEvent`, `EventEmitter`,
  `operation_emitter`, typed enums (`OperationKind`, `EventCategory`, `EventSeverity`,
  `EventPhase`); removed free-form `OperationEvent.stage`
- `spell_sync/application/event_presenter.py` — `present_event`, fixed message catalog,
  contextual overrides for `target_id` and `reason_code`
- `spell_sync/diagnostics/technical_event_log.py` — JSON Lines serialization
  (`schemaVersion: 1`), privacy field allowlist, `write_technical_event`,
  `parse_technical_log_line`, `format_log_line_for_display` for backward-compatible tail reading
- Focused services (`sync`, `recovery`, `setup`, `target_settings`) and
  `project_setup/execute.py`, `project_setup/target_settings.py` emit typed events with
  `correlation_id` from preview/plan identifiers
- `DiagnosticsService.finalize_report` emits `diagnostics.history_write_failed` on history
  append failure; `SpellSyncService` emits `diagnostics.logging_setup_failed` when file logging
  cannot start
- TUI `operation_screen.py` drives progress from `EventId` / `PresentedEvent` (replacing
  free-form stage strings)
- `safe_log.format_safe_log_record` bypasses sanitization for structured JSON lines;
  legacy plain-text lines remain redacted
- `read_technical_log_tail` displays structured events via presenter-friendly summaries
- ADR `docs/decisions/0004-structured-technical-events.md`
- `docs/PROJECT_MAP.md` and `tests/test-impact.toml` diagnostics/events cluster updated

### Required outcomes (delivered)

- typed event identifiers instead of arbitrary stage strings
- stable severity/category/operation metadata
- safe structured payload without user words (serialize-time forbidden keys)
- one canonical emission path via `operation_emitter` / `emit_technical`
- CLI/TUI convert events to presentation only (`EventSink` → `PresentedEvent`)
- technical file logging receives structured JSON Lines events
- history diagnostics and support workflows remain privacy-safe (no event stream in history)
- no parallel old/new event pipeline after migration
- internal JSON Lines boundary with `schemaVersion: 1` and backward tail reading for legacy lines

### Safety and privacy (preserved)

- no user dictionary words in events or technical log payloads
- no raw config, credentials, or journal contents in events
- HOME paths redacted on legacy log lines; structured events omit path fields
- logging failure does not block Pull/Push/Recovery
- product semantics, CLI JSON, and exit codes unchanged

### Deferred

- version `0.3.0`
- CLI redesign
- TUI redesign
- telemetry/network transport and remote logging (rejected — see ADR 0004)
- release/tag/publication

### Phase-specific validation (pending final CI)

```text
tests/test_technical_logging.py
tests/test_diagnostic_redaction.py
Pull/Push/Recovery safety suites
TUI architecture and mutation safety
privacy redaction on technical log tail
full final CI on committed clean HEAD
```

### Completion criteria (met pending approval)

- one structured event contract
- no duplicate event pipeline
- CLI/TUI adapters use presentation sinks
- privacy tests on logging and redaction paths
- application services emit typed events
- final CI on committed clean HEAD (pending)
- status `awaiting-approval`

## Phase 2B: complete application boundary

### CLI bypass inventory (resolved)

| Command | Before | After |
|---------|--------|-------|
| status | service | service |
| pull | CLI `SyncRun` | `prepare_pull` / `execute_pull` |
| push | CLI `SyncRun` + `prepare_push(run)` | `load_push_preview` / `execute_push_preview` |
| recover | journal internals in CLI | `inspect_recovery` + typed execution |
| doctor | `RuntimeResolver.sync_run` | `load_doctor_report` / `load_doctor_targets` |
| plan | `RuntimeResolver.sync_run` | `load_push_plan` / `execute_push_dry_run` |
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

Push strict resolution: `effective_push_strict()` in `project_resolution.py` (explicit
runtime settings from `ResolvedRuntime` / preview context).

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
- Phase 2C–2E: deterministic CI, agent workflow, test selection infrastructure
- Phase 3: explicit runtime, RuntimeIdentity, clean-tree final CI evidence (owner-approved)

## Last validation

```text
Phase 3 (accepted): HEAD 1ba73ba; full CI finalEvidence=true (20260721T040009.370414Z); 100% line coverage
Phase 2B: pytest 1559+ passed; scripts/ci.sh green (2026-07-20)
```

## Remaining work

Phases 4–10 on public spell-sync repository (see migration order). Phase 4 preflight
maintenance (NUL-safe untracked digest, snapshot Git timeout) before decomposition.

## Deferred work

- TUI flow split (`tui/flows/`) — only if controller refactor warrants it
- Developer stderr traceback mode — only if existing verbose path insufficient
