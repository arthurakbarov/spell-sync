# Supported environments

What you need to install and run Spell Sync.

## Python

| Scope | Support |
|-------|---------|
| Requirement (`requires-python`) | `>=3.14,<3.15` |
| CI | CPython 3.14 |

Spell Sync `1.0.0` supports **Python 3.14 only**.

Install with any PEP-compatible installer (`pip`, `uv`, etc.). The product does **not**
require `uv` at runtime.

## Platforms

| Platform | Support |
|----------|---------|
| macOS | Supported |
| Linux | Supported |
| Windows | Supported (some dictionary targets are capability-limited — see [Supported apps](SUPPORTED_APPS.md)) |

**Supported** means Collect / Update / TUI paths are implemented and covered by automated
tests. It does not mean every app has a recorded real-application sample on every OS.
See [Supported apps](SUPPORTED_APPS.md) for the honesty matrix.

## Related

- [Supported apps](SUPPORTED_APPS.md)
- [Getting Started](GETTING_STARTED.md)
