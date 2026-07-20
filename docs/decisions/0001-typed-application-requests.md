# Typed application requests

## Status

Accepted

## Context

Spell Sync 0.2.x routed CLI options and TUI state through `CliOptions` into
`SpellSyncService`, coupling the application layer to parser and presentation concerns.

## Decision

Introduce immutable UI-neutral request dataclasses in `spell_sync/application/requests.py`.
CLI maps `CliOptions` through `spell_sync/cli_request_adapter.py`; TUI builds requests
directly. `SpellSyncService` accepts typed requests only.

## Consequences

- Application and TUI no longer import `CliOptions`
- `application/requests.py` contains frozen DTOs only; resolution in `project_resolution.py`
- Core/project modules do not import application DTOs
- CLI mutation commands route through `SpellSyncService` (preflight scope preserves JSON exits)
- Presentation flags stay in CLI command handlers
- Confirmation tokens remain separate execution arguments
- `config-check` and `lint` remain CLI utilities without request types
- Runtime settings (`ContextVar`) unchanged in 0.2.1; explicit runtime deferred to Phase 3

## Rejected alternatives

- Parallel `CliOptions | Request` service signatures
- Passing raw argparse namespaces into the application layer
- Embedding JSON/export flags in application requests
