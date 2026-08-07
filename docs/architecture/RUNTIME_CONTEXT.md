# Runtime context

Runtime configuration and operation context are resolved explicitly. There is no
production `ContextVar` for settings or `ResolvedRuntime` and no module-level config cache.

## Resolution path

```text
ProjectRef / request
  → RuntimeResolver
  → ResolvedRuntime (config + journal + RuntimeIdentity)
  → RuntimeContext (wordlist, RuntimeSettings, dictionaries, strict_push)
  → sync_run / push_* / project_setup / diagnostics
```

`_runtime_factory` is private to resolution paths. CLI and TUI do not construct runtime
independently.

## Runtime identity

Preview operations store a deterministic `RuntimeIdentity` at plan time. Under the operation
lock, execution resolves fresh runtime and compares identity to the preview identity.

| Outcome | Behavior |
|---------|----------|
| Match | Proceed to fingerprint validation and writes |
| Mismatch | `STOPPED_SAFELY` — no automatic replan |

Fresh resolution happens under the project operation lock via `mutation_scope_for` /
`RuntimeResolver.mutation_scope`. Hidden reuse of preview-time runtime is forbidden.

## Settings

`settings.py` loads config per resolve via `load_config_result`. `RuntimeSettings` travels on
`RuntimeContext` — not through globals.

## Related modules

| Module | Role |
|--------|------|
| `application/runtime_resolver.py` | Canonical resolver |
| `application/_runtime_factory.py` | Private factory |
| `resolved_runtime.py` | Resolved bundle |
| `runtime_identity.py` | Preview/execute binding |
| `sync_context.py` | Wordlist + runtime settings context |
| `application/mutation_scope.py` | Lock-scoped mutation resolution |

See ADR [0002-explicit-runtime.md](../decisions/0002-explicit-runtime.md).
