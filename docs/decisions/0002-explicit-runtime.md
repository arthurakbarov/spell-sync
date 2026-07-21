# ADR 0002: Explicit runtime resolution

## Status

Accepted (Phase 3 complete)

## Context

Spell Sync 0.2.1 resolved project settings and validated runtime through module-level
`ContextVar` scopes (`_active_settings`, `_active_validated`). Dictionary discovery and
mutating command helpers read those implicit globals, which made runtime dependencies
hard to trace and test.

## Decision

- Remove production `ContextVar` usage for settings and validated runtime.
- Introduce `RuntimeResolver` in the application layer with optional `bound` reuse.
- Pass explicit settings dicts into dictionary discovery and config flag helpers.
- Resolve push strict mode from explicit runtime config when available.
- Core receives a prepared `RuntimeContext` / `ResolvedRuntime`; low-level factories stay private to resolution paths.
- `sync_run_for(resolved, …)` requires an explicit `ResolvedRuntime` — no config-loading fallback.
- Mutating commands acquire a fresh resolved runtime under the operation lock via `mutation_scope_for`.
- Prepared Pull/Push operations store a deterministic `RuntimeIdentity` at preview time. Under the operation lock, execution compares fresh identity to the preview identity before any writes. A mismatch stops safely with reason `runtime_changed_after_preview`; execution never replans automatically.

## Runtime identity invariant

A prepared operation is executable only while its `RuntimeIdentity` matches a fresh runtime
resolved under the operation lock. A changed runtime blocks execution; it never triggers
automatic replanning.

## Consequences

- Application facade owns runtime resolution; core modules no longer bind implicit scopes.
- CLI JSON, exit codes, and Pull/Push semantics remain unchanged.
- No module-level config cache and no `ContextVar` runtime scope; each resolve reads current config.
- Fresh mutation resolution happens under the project operation lock.
- Typed `RuntimeSettings` and `RuntimeResolver` form the application boundary.
- Service decomposition and structured technical events remain deferred to later phases.
