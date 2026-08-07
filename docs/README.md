# Spell Sync documentation

Navigation index for public repository documentation. Product semantics and safety rules live
in the linked canonical documents — not in implementation trackers or release diaries.

## For users

| Document | Contents |
|----------|----------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | First project, Pull, Push |
| [SUPPORTED_APPS.md](SUPPORTED_APPS.md) | End-user application list |
| [SUPPORTED_TARGETS.md](SUPPORTED_TARGETS.md) | Target capability matrix |
| [CONFIGURATION.md](CONFIGURATION.md) | `spell-sync.toml` reference |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Symptom-based guidance |
| [PERSONAL_WORKSPACE.md](PERSONAL_WORKSPACE.md) | Where the word list lives: local / synced folder / private Git |
| [PERSONAL_GIT_REMOTE.md](PERSONAL_GIT_REMOTE.md) | Optional private GitHub (or other) remote recipe |
| [RECOVERY.md](RECOVERY.md) | Transaction journal and `recover` |

## For contributors

| Document | Contents |
|----------|----------|
| [DEVELOPMENT.md](DEVELOPMENT.md) | Setup, CI, local validation |
| [ENGINEERING_COMPLETION.md](ENGINEERING_COMPLETION.md) | Repo/agent done-definition |
| [PRODUCT_COMPLETION.md](PRODUCT_COMPLETION.md) | Product UX / release readiness |
| [CONTRACTS.md](CONTRACTS.md) | Doctor/status/TUI state vocabulary |
| [FEATURE_MATRIX.md](FEATURE_MATRIX.md) | Feature honesty (automated vs manual) |
| [INVENTORY.md](INVENTORY.md) | Maintainer / manual / non-repo items |
| [WORKFLOW.md](WORKFLOW.md) | Operator edit / checkpoint / full-gate loop |
| [ARTIFACTS-AND-STATE.md](ARTIFACTS-AND-STATE.md) | Local vs shareable artifacts |
| [OPERATIONS.md](OPERATIONS.md) | Failure runbooks tied to CONTRACTS |
| [ROADMAP.md](ROADMAP.md) | Open completion blockers only |
| [AGENT_DEVELOPMENT.md](AGENT_DEVELOPMENT.md) | Agent workflow and evidence contracts |
| [GIT-WORKFLOW.md](GIT-WORKFLOW.md) | Commit shape, split discipline, push policy |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Focused test levels and selection |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Pull requests |
| [PROJECT_MAP.md](PROJECT_MAP.md) | Module ownership map |

## Architecture

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Product model, command flow, core modules |
| [architecture/APPLICATION_LAYER.md](architecture/APPLICATION_LAYER.md) | Requests, facade, services |
| [architecture/RUNTIME_CONTEXT.md](architecture/RUNTIME_CONTEXT.md) | Explicit runtime resolution |
| [architecture/MUTATION_SAFETY.md](architecture/MUTATION_SAFETY.md) | Preview, lock, journal invariants |
| [architecture/DIAGNOSTICS.md](architecture/DIAGNOSTICS.md) | Events, logs, history, privacy |
| [architecture/TARGET_MODEL.md](architecture/TARGET_MODEL.md) | Discovery, capabilities, validation |
| [TUI_IMPLEMENTATION.md](TUI_IMPLEMENTATION.md) | Textual screens and flows |
| [TUI_LAYOUT.md](TUI_LAYOUT.md) | Shared TUI shell, actions, tables, duration hints |
| [decisions/](decisions/) | Architecture decision records (ADRs) |

Implementation phase tracker (maintainer/architect use): [ARCHITECTURE_V1_IMPLEMENTATION.md](ARCHITECTURE_V1_IMPLEMENTATION.md) (Version 1 architecture).

## Safety and recovery

| Document | Contents |
|----------|----------|
| [RECOVERY.md](RECOVERY.md) | Journal, snapshots, recovery commands |
| [architecture/MUTATION_SAFETY.md](architecture/MUTATION_SAFETY.md) | Application-level safety contracts |

## Diagnostics

| Document | Contents |
|----------|----------|
| [architecture/DIAGNOSTICS.md](architecture/DIAGNOSTICS.md) | Technical events, logs, history |
| [technical/](technical/) | Machine-readable schemas and contracts |
| [technical/doctor-report.schema.json](technical/doctor-report.schema.json) | Doctor JSON payload schema |
| [technical/target-validation.schema.json](technical/target-validation.schema.json) | Manual target validation matrix schema |
| [examples/target-validation-entry.example.json](examples/target-validation-entry.example.json) | Example matrix entry for platform-validation |

## Targets and validation

| Document | Contents |
|----------|----------|
| [SUPPORTED_TARGETS.md](SUPPORTED_TARGETS.md) | Public target registry |
| [SUPPORTED_ENVIRONMENTS.md](SUPPORTED_ENVIRONMENTS.md) | Python and platform support |
| [MANUAL_TESTING.md](MANUAL_TESTING.md) | Human release checklist |
| [target-validation.json](target-validation.json) | Manual validation matrix (data) |

## Maintainers

| Document | Contents |
|----------|----------|
| [EXECUTION_TIME_CONTROL.md](EXECUTION_TIME_CONTROL.md) | CI timing and admission |
| [AGENT_DEVELOPMENT.md](AGENT_DEVELOPMENT.md) | Evidence, snapshot, agent rules |
| [ARCHITECTURE_V1_IMPLEMENTATION.md](ARCHITECTURE_V1_IMPLEMENTATION.md) | Version 1 architecture tracker |
| [DEAD_DIRECTORY_AUDIT.md](DEAD_DIRECTORY_AUDIT.md) | Maintainer workspace dead-path inventory (report only) |

Private maintainer tooling and snapshot policy live in the separate `spell-sync-dev`
repository (not shipped with this package).
