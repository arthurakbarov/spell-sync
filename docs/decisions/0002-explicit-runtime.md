# ADR 0002: Explicit runtime resolution

## Status

Accepted (Phase 3, awaiting owner approval)

## Context

Spell Sync 0.2.1 resolved project settings and validated runtime through module-level
`ContextVar` scopes (`_active_settings`, `_active_validated`). Dictionary discovery and
mutating command helpers read those implicit globals, which made runtime dependencies
hard to trace and test.

## Decision

- Remove production `ContextVar` usage for settings and validated runtime.
- Introduce `RuntimeResolver` in the application layer with optional `bound` reuse.
- Pass explicit settings dicts into dictionary discovery and config flag helpers.
- Pass optional `validated` / `bound` parameters through `runtime_context_for`,
  `sync_run_for`, and `mutating_command_scope_for`.
- Resolve push strict mode from explicit runtime config when available.

## Consequences

- Application facade owns runtime resolution; core modules no longer bind implicit scopes.
- CLI JSON, exit codes, and Pull/Push semantics remain unchanged.
- Module-level settings cache remains for performance; explicit config bypasses reload paths.
- Service decomposition and structured technical events remain deferred to later phases.
