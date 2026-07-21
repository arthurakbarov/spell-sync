# Project map (application layer)

Canonical module responsibilities after Phase 4 service decomposition.

## Facade

| Module | Role |
|--------|------|
| `spell_sync/application/service.py` | Thin `SpellSyncService` compatibility facade for CLI and TUI |

## Focused services

| Module | Role |
|--------|------|
| `application/services/context.py` | Shared `ApplicationContext` (runtime, history, paths) |
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
| `application/reports.py` | Report and execution dataclasses |
| `application/runtime_resolver.py` | Explicit runtime resolution |

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

See also `docs/ARCHITECTURE.md` and `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md`.
