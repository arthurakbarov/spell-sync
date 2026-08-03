# Application layer

Spell Sync routes CLI and TUI through one UI-neutral application boundary before core
mutation logic runs.

## Entry points

| Surface | Path into application |
|---------|----------------------|
| CLI | `cli_request_adapter.py` maps `CliOptions` → typed requests |
| TUI | Controller builds requests directly |
| Both | `SpellSyncService` facade → focused services |

`CliOptions` is a CLI parser DTO only. Application code, TUI, and core must not depend on it.

## Typed requests

Immutable dataclasses in `spell_sync/application/requests.py`:

| Request | Role |
|---------|------|
| `ProjectRef` | Wordlist / project selection |
| `StatusRequest` | Status and diff detail |
| `DoctorRequest` | Doctor and target health |
| `PullRequest` / `PushRequest` | Pull/Push preview and execution |
| `RecoveryRequest` | Recovery inspection and execution |
| `SetupRequest` | Project setup |
| `TargetSettingsRequest` | Per-target settings load/update |
| `SupportReportRequest` | Support report export |

`config-check` and `lint` remain CLI utilities without request types.

See ADR [0001-typed-application-requests.md](../decisions/0001-typed-application-requests.md).

## Focused services

| Service | Responsibility |
|---------|----------------|
| `DiagnosticsService` | History, technical log, support report |
| `InspectionService` | Status, dashboard, doctor |
| `SyncService` | Pull/Push preview and execution |
| `RecoveryService` | Recovery preview and execution |
| `SetupService` | Project setup |
| `TargetSettingsService` | Target settings load and update |

`SpellSyncService` is a thin delegation facade. Shared wiring uses frozen `ApplicationContext`.

See ADR [0003-focused-application-services.md](../decisions/0003-focused-application-services.md)
and [PROJECT_MAP.md](../PROJECT_MAP.md).

## Allowed dependencies

```text
CLI / TUI
  → application requests
  → SpellSyncService / services/*
  → RuntimeResolver
  → core (sync_run, push_*, pull, project_setup)

core / project_setup
  ✗ must not import spell_sync.application
```

Enforced by `scripts/check_architecture.py` (`architecture.boundaries` CI check).

## Presentation

- Builders in `application/builders.py` assemble UI-neutral view models.
- `event_presenter.py` maps `EventId` → user-facing copy at CLI/TUI boundaries only.
- Mutation orchestration stays in services and core — not in builders or the facade.
