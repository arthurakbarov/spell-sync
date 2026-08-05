# Project map

Agent-friendly module ownership map for Spell Sync. Product semantics live in
`docs/ARCHITECTURE.md`; mutation safety in `docs/RECOVERY.md`.

## Entry points

| Entry | Module | Role |
|-------|--------|------|
| CLI | `spell_sync/cli.py`, `spell_sync/commands.py`, `*_cmd.py` | Parse args, map to typed requests, render JSON/text |
| CLI adapter | `spell_sync/cli_request_adapter.py` | Sole production mapper from `CliOptions` to application requests |
| TUI | `spell_sync/tui/app.py`, `spell_sync/tui/controller.py` | Textual screens; build requests directly; call `SpellSyncService` |
| Application facade | `spell_sync/application/service.py` | Thin compatibility facade for CLI and TUI |
| Core orchestration | `spell_sync/sync_run.py`, `spell_sync/push_prepared.py`, `spell_sync/application/services/sync.py` | Pull/Push execution after application preview binding |

No-args on a TTY launches the TUI when the project is ready.

## Layers and allowed dependencies

```text
CLI / TUI
  → typed application requests
  → SpellSyncService (facade)
  → application/services/*
  → RuntimeResolver
  → core (sync_run, push_*, project_setup, diagnostics)

Settings (settings.py)
  → load_config_result per resolve (no module settings cache)
  → RuntimeSettings on RuntimeContext
```

Rules:

- Focused services must not import CLI, TUI, Textual, or `CliOptions`.
- Core and `project_setup` must not import `spell_sync.application`.
- Mutation paths resolve fresh runtime under the operation lock via `RuntimeResolver`.
- TUI must not subprocess the CLI or call low-level dictionary writers directly.

## Application requests

Immutable DTOs in `spell_sync/application/requests.py`:

| Request | Purpose |
|---------|---------|
| `ProjectRef` | Unresolved wordlist selection |
| `StatusRequest` | Status / diff detail |
| `DoctorRequest` | Doctor and target health |
| `PullRequest` | Pull preview and execution |
| `PushRequest` | Push preview and execution |
| `RecoveryRequest` | Recovery inspection and execution |
| `SetupRequest` | Project setup / init |
| `TargetSettingsRequest` | Load per-target settings |
| `PrepareTargetSettingsUpdateRequest` | Target settings preview |
| `SupportReportRequest` | Support report export |

`config-check` and `lint` remain CLI utilities without request types.

## Services

| Module | Role |
|--------|------|
| `application/services/context.py` | Shared frozen `ApplicationContext` |
| `application/services/diagnostics.py` | History, technical log, support report |
| `application/services/inspection.py` | Status, dashboard, doctor |
| `application/services/sync.py` | Pull/Push preview and execution |
| `application/services/recovery.py` | Recovery preview and execution |
| `application/services/setup.py` | Project setup / init |
| `application/services/target_settings.py` | Target settings load and update |

Presentation helpers: `application/builders.py`, `application/event_presenter.py`,
`application/reports.py` (stable re-export of canonical DTOs), `operation_reports.py`
(canonical DTOs), `application/runtime_resolver.py`.

## Core mutation modules

| Module | Role |
|--------|------|
| `push_prepared.py` | Prepared push execution and fingerprint binding |
| `push_transaction.py` | Atomic dictionary writes inside transactions |
| `push_journal.py` | Journal lifecycle for Push |
| `sync_run.py` | Shared sync runtime; Pull union into wordlist |
| `mutation_guards.py` | Shared mutation safety helpers |
| `operation_lock.py` | Per-project exclusive mutation lock |
| `secure_artifacts.py` | Symlink/reparse-safe lock, journal, and txn paths |
| `trusted_internal_fs.py` | Descriptor-relative trusted internal filesystem |
| `journal_schema.py` | Journal schema versions and validation |
| `runtime_identity.py` | Immutable identity bound to prepared mutations |
| `resolved_runtime.py` | Resolved runtime snapshot for operations |
| `application/mutation_scope.py` | Operation lock + fresh runtime resolution |

Preview objects carry `RuntimeIdentity`; execution re-resolves under lock and stops safely on
mismatch.

## Diagnostics and history

| Module | Role |
|--------|------|
| `diagnostics/technical_event_model.py` | Typed `EventId`, `TechnicalEvent` |
| `diagnostics/technical_event_log.py` | JSON Lines serialization and tail parsing |
| `diagnostics/technical_logging.py` | Rotating technical log handler |
| `diagnostics/safe_log.py` | Legacy plain-text redaction |
| `diagnostics/history_store.py` | Compact user-facing operation history |
| `application/events.py` | `EventEmitter`, presentation-neutral emission |

Technical events are privacy-safe; history stores summaries only.

## TUI flows

| Area | Module(s) |
|------|-----------|
| Controller | `tui/controller.py` |
| Launch routing | `tui/routing.py` (`should_launch_tui`, non-interactive errors) |
| Dashboard | `tui/screens/dashboard.py` |
| Collect / Pull / Push / Preview / Confirm | `tui/screens/*` |
| Setup wizard | `tui/screens/setup_*` |
| Target settings | `tui/screens/target_settings_screen.py` |
| Operation progress | `tui/screens/operation_screen.py` driven by `PresentedEvent` |

Workers call the service protocol; screens never import journal or transaction writers.

## Target discovery

| Module | Role |
|--------|------|
| `dictionary_registry.py` | Register dictionary sources |
| `dictionaries.py` | Read/write custom dictionaries |
| `target_capabilities.py` | Supported target metadata |
| `project_setup/discovery.py` | Setup-time target discovery |
| `config.py` / `settings.py` | Target enablement from `spell-sync.toml` |

Built-in application dictionaries are never inspected or modified.

## Package resources

| Path | Role |
|------|------|
| `spell_sync/bundled/spell-sync.toml.example` | Example project config |
| `spell_sync/bundled/wordlist.txt.example` | Example wordlist |
| `spell_sync/bundled/lint-whitelist.txt` | Lint allowlist shipped with the package |

## Test suites by responsibility

Architecture guards: `tests/test_application_requests.py`, `tests/test_application_services.py`,
`tests/test_runtime_architecture.py`, `tests/tui/test_architecture.py`,
`tests/test_check_architecture.py`.

Safety: `tests/test_pull_safety.py`, `tests/test_transaction_safety.py`,
`tests/test_tui_mutation_safety.py`, `tests/test_tui_recovery_safety.py`.

[project-map:start]
_Generated by `scripts/check_architecture.py` from `ci/test-groups.toml`; do not edit manually._

| Group | Responsibility |
|-------|----------------|
| `tests:tui` | TUI screens, navigation, wizard, and smoke tests |
| `tests:dev-tooling` | CI timing, admission, evidence, test selection, and agent tooling |
| `tests:environment` | Environment contract, compatibility, and snapshot policy |
| `tests:packaging` | Wheel install, packaging, and installed smoke |
| `tests:integration` | Slow multi-step and subprocess integration flows |
| `tests:rest` | Unclaimed remainder tests (fallback group) |

Run grouped CI via `scripts/ci_runner.py` or `scripts/ci.sh`.
[project-map:end]

## Common change recipes

| Change | Start here | Also update |
|--------|------------|-------------|
| New application target | skill `add-target`, `target_capabilities.py`, dictionary adapter | `docs/SUPPORTED_APPS.md`, config schema, discovery tests |
| Pull/Push behavior | `application/services/sync.py`, core mutation modules | safety tests, `docs/RECOVERY.md` if invariants shift |
| TUI screen | `tui/screens/`, `tui/controller.py` | `tests/tui/`, architecture tests |
| Structured technical event | `diagnostics/technical_event_model.py`, `event_presenter.py` | privacy tests, ADR if contract changes |
| Agent workflow / CI | `scripts/ci_runner.py`, `.cursor/skills/` | `docs/AGENT_DEVELOPMENT.md`, validators |

See also `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md`, `docs/TESTING_STRATEGY.md`, and ADRs under
`docs/decisions/`.

## Execution control (toolchain)

Stdlib-only infrastructure under `scripts/execution_control/` — development/CI runners only, not
part of the product application layer. Canonical reference: `docs/EXECUTION_TIME_CONTROL.md`.
