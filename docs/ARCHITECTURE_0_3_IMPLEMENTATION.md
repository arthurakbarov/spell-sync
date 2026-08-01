# Spell Sync 0.3 architecture implementation

## Goal

Prepare architectural release 0.3.0: typed application requests, explicit runtime
context, thin facade with focused services, structured technical events, current
documentation, and architecture validation guards.

Remove obsolete private maintainer export workflow (completed in spell-sync-dev).

## Current phase

Phase 7: documentation reorganization and ADRs — **complete** (owner-approved).
Phase 8: agent configuration refresh — **complete** (owner-approved).
Phase 9: dead directory audit — **complete** (owner-approved).
Phase 10: version 0.3.0 — **complete**, awaiting approval.

Corrective work (security hardening, post-review): in progress on current branch — descriptor/handle
trusted internal filesystem, R1–R7 adversarial regressions, recovery outcome propagation to CLI/TUI,
explicit backup policy; does not advance phase-10 approval or start a new architecture phase.

[architecture-status:start]
current: phase-10
phase-1: complete
phase-2: complete
phase-2b: complete
phase-2c: complete
phase-2d: complete
phase-2e: complete
phase-3: complete
phase-4: complete
phase-5: complete
phase-6: complete
phase-7: complete
phase-8: complete
phase-9: complete
phase-10: awaiting-approval
[architecture-status:end]

## Verified baseline

| Repository | HEAD | Clean |
|------------|------|-------|
| spell-sync | `9f5e83c` Phase 10 tracker baseline aligned | yes |
| spell-sync-dev | `5765e7d` health check uses CI evidence | yes |
| spell-words | `3e5bc29` | yes |

Public version: `0.3.0` (`pyproject.toml`).

Phase 5 final CI evidence: `7985302`, run `20260723T034038.010703Z`, `finalEvidence=true`.

Phase 6 final CI evidence: `f82ed58`, run `20260728T074706.122702Z`, `finalEvidence=true`.

Phase 7 final CI evidence: `9a08a7e`, run `20260731T101824.828581Z`, `finalEvidence=true`.

Phase 8 final CI evidence: `3c6bc35`, run `20260731T104234.254905Z`, `finalEvidence=true`.

Phase 10 final CI evidence: `e46ce45`, run `20260731T110156.184380Z`, `finalEvidence=true`.

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
9. ~~Dead directory audit~~ done
10. ~~Version 0.3.0~~ done (awaiting approval)

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

**Status:** complete (owner-approved)

### Owner acceptance (recorded)

- typed technical events with JSON Lines schema v1;
- polish arc: user-first onboarding, timing observability, dependency groups, consistency validators;
- final CI evidence bound to HEAD `7985302`, run `20260723T034038.010703Z`;
- package version remains `0.2.1`.

## Phase 6 — Architecture validator and project map

**Status:** complete (owner-approved)

### Goal

Add automated architecture boundary validation and an agent-friendly project map with
generated test-group coverage for safe, incremental changes.

### Delivered

- `scripts/check-architecture.py` — AST-based dependency guards, request/event export checks,
  project map heading sync, generated test-group section validation
- `docs/PROJECT_MAP.md` — ownership map with generated test suites by responsibility
- CI check `architecture.boundaries` wired into `scripts/ci_runner.py`
- focused tests in `tests/test_check_architecture.py`

### Phase-specific validation (passed)

```text
tests/test_check_architecture.py
tests/test_application_requests.py
tests/test_application_services.py
tests/test_runtime_architecture.py
tests/tui/test_architecture.py
full final CI on committed clean HEAD f82ed58
```

### Completion criteria (met)

- architecture validator enforces layer boundaries and public application exports
- project map matches validator-required headings and test-group registry
- CI gate `architecture.boundaries` passes on final evidence HEAD
- owner approval recorded; tracker status `complete`

### Owner acceptance (recorded)

- architecture validator and expanded project map delivered;
- final CI evidence bound to HEAD `f82ed58`, run `20260728T074706.122702Z`;
- package version remains `0.2.1`.

## Phase 7 — Documentation reorganization and ADRs

**Status:** complete (owner-approved)

### Goal

Documentation describes the current system — not prompt history or implementation diaries.

### Delivered

- `docs/README.md` — navigation index (users, contributors, architecture, safety, diagnostics,
  targets, maintainers)
- `docs/architecture/` — focused layer guides (`APPLICATION_LAYER`, `RUNTIME_CONTEXT`,
  `MUTATION_SAFETY`, `DIAGNOSTICS`, `TARGET_MODEL`)
- Updated `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/MANUAL_TESTING.md`
- Normalized ADR status sections in `docs/decisions/0002`–`0004`
- Removed obsolete `docs/UX_0_2_IMPLEMENTATION.md` and `docs/platform-validation-readiness.md`
- `scripts/check-docs-contract.py` historical doc list updated

### Phase-specific validation (passed)

```text
python3 scripts/check-docs-contract.py
python3 scripts/check-docs-style.sh
python3 scripts/check-agent-config.py
full final CI on committed clean HEAD 9a08a7e
```

### Owner acceptance (recorded)

- documentation index and architecture layer guides delivered;
- obsolete implementation diaries removed;
- final CI evidence bound to HEAD `9a08a7e`, run `20260731T101824.828581Z`;
- package version remains `0.2.1`.

## Phase 8 — Agent configuration refresh

**Status:** complete (owner-approved)

### Goal

Refresh public agent configuration (rules, skills, `AGENTS.md`, validator) for the 0.3
architecture without handoff or reviewer-specific workflow language.

### Delivered

- `AGENTS.md` — current architecture map, services, explicit runtime, diagnostics, validation commands
- Updated rules: `architecture-boundaries`, `project-safety`, `tui`, `tests-fixtures`, `packaging-privacy`
- New skill `diagnostics-change`; updated `architecture-refactor`
- `scripts/check-agent-config.py` — requires `diagnostics-change`, bans stale runtime and handoff terms

### Phase-specific validation (passed)

```text
python3 scripts/check-agent-config.py
python3 scripts/check-docs-contract.py
python3 scripts/check-architecture.py --check
full final CI on committed clean HEAD 3c6bc35
```

### Owner acceptance (recorded)

- agent rules, skills, `AGENTS.md`, and validator refreshed for 0.3 architecture;
- final CI evidence bound to HEAD `3c6bc35`, run `20260731T104234.254905Z`;
- package version remains `0.2.1`.

## Phase 9 — Dead directory audit

**Status:** complete (owner-approved)

### Goal

Inventory obsolete and generated paths in the maintainer workspace (`~/code/`). Report
only — no automated deletion.

### Delivered

- `docs/DEAD_DIRECTORY_AUDIT.md` — categorized inventory (safe generated, obsolete,
  likely stale, keep, stashes)
- Linked from `docs/README.md` (Maintainers)

### Phase-specific validation (passed)

```text
python3 scripts/check-agent-config.py
python3 scripts/check-docs-contract.py
python3 scripts/run_lightweight_validation.py
python3 scripts/check-ci-evidence.py
```

### Owner acceptance (recorded)

- dead directory audit report delivered (`docs/DEAD_DIRECTORY_AUDIT.md`);
- report-only scope honored — no paths deleted;
- lightweight validation and CI evidence reuse bound to HEAD `7d11b45`;
- package version remains `0.2.1` until Phase 10.

## Phase 10 — Version 0.3.0

**Status:** awaiting approval

### Goal

Bump public package version to `0.3.0` reflecting the completed 0.3 architecture migration.
No tag, release, or publication in this phase.

### Delivered

- `pyproject.toml` and `uv.lock` — `0.3.0`
- Compatibility and installed-wheel tests aligned; `run_compatibility_checks.py` reads version from `pyproject.toml`
- `check-docs-contract.py` — stale-version guard covers `0.2.0`/`0.2.1`; ADRs exempt

### Phase-specific validation (passed)

```text
python3 scripts/check-docs-contract.py
python3 scripts/check-agent-config.py
full final CI on committed clean HEAD e46ce45
spell-sync version → 0.3.0
CI_EVIDENCE_MATCH=exact-head
```

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
- Phase 4: focused application services and thin facade (owner-approved)
- Phase 5: structured technical events and polish (owner-approved)
- Phase 6: architecture validator and project map (owner-approved)
- Phase 7: documentation reorganization and ADRs (owner-approved)
- Phase 8: agent configuration refresh (owner-approved)
- Phase 9: dead directory audit (owner-approved)

## Last validation

```text
Phase 10 (awaiting approval): HEAD 9069783; full CI finalEvidence=true (20260731T110156.184380Z @ e46ce45); version 0.3.0
Phase 9 (accepted): HEAD 7d11b45; lightweight validation; CI_EVIDENCE_MATCH=reused-non-ci-change
Phase 8 (accepted): HEAD 3c6bc35; full CI finalEvidence=true (20260731T104234.254905Z)
Phase 7 (accepted): HEAD 9a08a7e; full CI finalEvidence=true (20260731T101824.828581Z)
Phase 6 (accepted): HEAD f82ed58; full CI finalEvidence=true (20260728T074706.122702Z); architecture.boundaries pass
Phase 5 (accepted): HEAD 7985302; full CI finalEvidence=true (20260723T034038.010703Z)
Phase 3 (accepted): HEAD 1ba73ba; full CI finalEvidence=true (20260721T040009.370414Z); 100% line coverage
```

## Remaining work

0.3 architecture migration complete pending Phase 10 owner acceptance. No further
phases in the migration order. Release/tag/publication remain owner-initiated only.

## Deferred work

- TUI flow split (`tui/flows/`) — only if controller refactor warrants it
- Developer stderr traceback mode — only if existing verbose path insufficient
