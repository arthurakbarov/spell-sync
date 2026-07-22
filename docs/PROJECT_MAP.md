# Project map (application layer)

Canonical module responsibilities after Phase 4 service decomposition and Phase 5 structured
events.

## Facade

| Module | Role |
|--------|------|
| `spell_sync/application/service.py` | Thin `SpellSyncService` compatibility facade for CLI and TUI |

## Focused services

| Module | Role |
|--------|------|
| `application/services/context.py` | Shared frozen `ApplicationContext` (runtime, history, paths) |
| `application/services/diagnostics.py` | Operation history, technical log, support report, report finalization |
| `application/services/inspection.py` | Status, dashboard, doctor (read-only) |
| `application/services/sync.py` | Pull/Push preview and execution orchestration |
| `application/services/recovery.py` | Recovery preview and execution |
| `application/services/setup.py` | Project setup / init |
| `application/services/target_settings.py` | Target settings load and update |

## Presentation (unchanged in Phase 4)

| Module | Role |
|--------|------|
| `application/builders.py` | UI-neutral snapshot and preview builders |
| `application/events.py` | Typed technical events (`EventId`, `TechnicalEvent`, `EventEmitter`) |
| `application/event_presenter.py` | Map `TechnicalEvent` → `PresentedEvent` for CLI/TUI |
| `application/reports.py` | Report and execution dataclasses |
| `application/runtime_resolver.py` | Explicit runtime resolution |

## Diagnostics (Phase 5)

| Module | Role |
|--------|------|
| `diagnostics/technical_event_log.py` | JSON Lines serialization, parse, and tail display for structured events |
| `diagnostics/technical_logging.py` | Rotating file handler; tail reads via structured line formatter |
| `diagnostics/safe_log.py` | Redaction for legacy plain-text log lines; structured JSON bypass |

## Dependency direction

```text
CLI / TUI
  → SpellSyncService (facade)
  → application/services/*
  → RuntimeResolver
  → core (sync_run, push_*, pull, project_setup, diagnostics)
```

Rules:

- Focused services must not import CLI, TUI, or Textual modules.
- Core modules must not import `spell_sync.application.services`.
- Mutation paths resolve fresh runtime under the operation lock via `RuntimeResolver`.

See also `docs/ARCHITECTURE.md` and `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md`. ADR:
`docs/decisions/0004-structured-technical-events.md`.

## Execution control (toolchain)

Stdlib-only infrastructure under `scripts/execution_control/` — not part of the product
application layer. Wraps development and CI runners only.

| Module | Role |
|--------|------|
| `admission.py` | CI necessity integration, edit-loop budget, reuse decisions |
| `context.py` | Normalized platform, Python, and workload bucket |
| `controller.py` | Immutable plan, bounded run, span persistence |
| `diagnostics.py` | Bounded timeout investigation bundles |
| `history.py` | SQLite spans, leases, learning samples |
| `identity.py` | Workload and policy fingerprints |
| `mappings.py` | Stable execution IDs for CI checks and gates |
| `models.py` | `ExecutionPlan`, `SpanRecord`, status enums |
| `prediction.py` | Expected, soft, stall, hard thresholds |
| `process_tree.py` | Owned process-group execution and termination |
| `progress.py` | Progress contracts for stall observation |
| `registry.py` | Load `tests/execution-budget.toml` |
| `reporting.py` | Machine-readable `EXECUTION_*` stdout |
| `session.py` | Edit-loop test-time share accounting |
| `statistics.py` | Robust duration statistics |

Entry points: `scripts/run_with_budget.py`, `scripts/validate_execution_budget.py`,
`scripts/execution_budget_report.py`, `scripts/execution_budget_admin.py`.

Canonical reference: `docs/EXECUTION_TIME_CONTROL.md`.
