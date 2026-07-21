# ADR 0003: Focused application services

## Status

Implemented — awaiting phase approval

## Context

`SpellSyncService` grew into a monolithic facade (~1500 lines) mixing inspection,
Pull/Push orchestration, Recovery, setup, target settings, and diagnostics. CLI and
TUI already depend on a single application entry point; Phase 3 introduced explicit
runtime resolution through `RuntimeResolver`.

Phase 4 must split responsibilities without changing Pull/Push semantics, CLI JSON,
exit codes, or preview/execution safety contracts.

## Decision

1. Introduce `spell_sync/application/services/` with focused, UI-neutral services:
   - `DiagnosticsService` — history, technical log, support report, report finalization
   - `InspectionService` — status, dashboard, doctor
   - `SyncService` — Pull/Push preview and execution
   - `RecoveryService` — Recovery preview and execution
   - `SetupService` — project setup
   - `TargetSettingsService` — target settings updates

2. Share dependencies through frozen `ApplicationContext` (`RuntimeResolver`,
   `OperationHistoryStore`, `AppStatePaths`). Wiring references are immutable after
   construction; dependency internal state remains mutable.

3. Keep `SpellSyncService` as a thin compatibility facade that delegates 1:1 to focused
   services without private operation orchestration helpers. CLI and TUI continue to call
   the facade only.

4. Keep shared low-level mutation imports in `_operation_deps.py` for focused services only;
   the facade must not import or re-export `_operation_deps`.

5. Leave presentation builders in `application/builders.py`; mutation orchestration lives
   in sync/recovery/setup/target services, not in builders or the facade.

6. Preflight maintenance (before decomposition):
   - NUL-safe untracked path parsing in `scripts/test_selection/tree_state.py`
   - subprocess timeout for production `_git_command()` in spell-sync-dev snapshot tooling

## Consequences

### Positive

- Single owner per application responsibility; easier review and testing
- Facade line count reduced substantially while preserving public API
- Architecture tests guard delegation and reverse dependencies
- `docs/PROJECT_MAP.md` documents the application module map

### Negative / constraints

- Some cross-service wiring (dashboard → diagnostics history) requires explicit constructor
  dependencies within the application layer
- Large sync/recovery modules remain; further presenter/orchestration splits are out of
  scope for Phase 4

## Compliance

Verified by:

- `tests/test_application_services.py`
- existing runtime identity, Pull/Push/Recovery safety, and TUI architecture tests
- full CI on committed clean HEAD
