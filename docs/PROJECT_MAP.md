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
