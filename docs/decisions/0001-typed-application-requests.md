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
- Presentation flags stay in CLI command handlers
- Confirmation tokens remain separate execution arguments
- Runtime settings (`ContextVar`) unchanged in 0.2.1

## Rejected alternatives

- Parallel `CliOptions | Request` service signatures
- Passing raw argparse namespaces into the application layer
- Embedding JSON/export flags in application requests
