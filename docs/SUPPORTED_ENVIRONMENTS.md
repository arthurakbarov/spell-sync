# Supported environments

Spell Sync separates **product runtime support** (what end users need to install and run
the tool) from **maintainer tooling support** (what contributors and CI use to build, test,
and snapshot the project).

The committed environment contract is the machine-readable source for maintainer Python,
dependency ownership, and platform claims: `config/environment-contract.toml`.

## Product Python

| Scope | Support |
|-------|---------|
| Public requirement (`project.requires-python`) | `>=3.11` |
| Blocking compatibility (CI) | CPython 3.11, CPython 3.12 |
| Experimental (non-blocking CI) | CPython 3.13 |
| Canonical maintainer interpreter | CPython 3.12.13 (`.python-version`) |

The committed `.python-version` file pins the **maintainer** interpreter. It does not replace
`requires-python` and is not the public support range.

End users install the wheel with any PEP-compatible installer (`pip`, `uv`, etc.). Product
runtime does **not** require `uv`.

## Product platforms

Target platforms for Pull/Push/TUI product behavior:

| Platform | Product support | Evidence |
|----------|-----------------|----------|
| macOS | Supported | CI compatibility matrix, synthetic tests |
| Linux | Supported | CI compatibility matrix, synthetic tests |
| Windows | Supported | CI compatibility matrix, synthetic tests |

Classifiers currently list `Operating System :: OS Independent`. Platform-specific dictionary
paths and filesystem behavior are validated in CI; real-application manual validation is
tracked separately in `docs/platform-validation-readiness.md`.

## Maintainer tooling

### Local development environment

| Component | Requirement |
|-----------|-------------|
| Dependency owner | `pyproject.toml`, `uv.lock`, `uv` |
| Canonical Python | CPython 3.12.13 via `.python-version` |
| Virtual environment | Disposable `.venv/` (local, ignored, not snapshotted) |
| Normal commands | Locked, offline, no implicit Python download or sync |
| Bootstrap | Explicit `python3 scripts/project_environment.py bootstrap --allow-python-download` only |

### CI architecture

| Job kind | Purpose |
|----------|---------|
| Canonical full CI | One blocking Ubuntu + Python 3.12 job running the full `scripts/ci.sh` gate |
| Compatibility | Narrow checks on Ubuntu 3.11, macOS 3.12, Windows 3.12 |
| Experimental | Ubuntu + Python 3.13, `continue-on-error`, product subset only |

Compatibility jobs must not duplicate the full CI gate (Ruff, mypy, full coverage, docs
validators, packaging suite, etc.).

### POSIX execution supervision

Advanced parent/child process-tree supervision (execution time control, owned process
termination) is supported on:

- macOS
- Linux

On Windows, tooling uses bounded subprocess fallback without POSIX process-group guarantees.

### Owner workspace snapshot

Creating the owner-controlled workspace archive (`$HOME/code.zip`) is supported on the
maintainer macOS owner environment. Snapshot policy lives in private `spell-sync-dev`
(`snapshot-policy.toml`).

The archive stores declarations and compact evidence, not disposable `.venv` directories or
execution-control SQLite history.

### Portable artifact verifier

Structural snapshot verification requires only stdlib Python `>=3.11` and Git where
required. It does not require `uv`, a synchronized `.venv`, or network access.

## Upgrade policies

| Change | Scope | Required follow-up |
|--------|-------|--------------------|
| Python patch (e.g. 3.12.13 → 3.12.x) | Maintainer only | Update `.python-version`, environment contract, recreate `.venv`, invalidate environment fingerprint, run focused tests and CI necessity |
| Python minor (e.g. 3.12 → 3.13) | Separate arc | Contract, lock, matrix, support policy, full CI |
| `uv` version | Toolchain commit | Pin in `pyproject.toml`, `[tool.uv]`, contract, lock check, environment recreate |
| Dependency mutation | Declarations | `uv add`/`uv remove`, review lock, sync, check, focused tests |

Do not run `uv self update` in project automation.

## Related documents

- `config/environment-contract.toml` — maintainer contract SSOT
- `docs/DEVELOPMENT.md` — contributor setup overview
- `docs/AGENT_DEVELOPMENT.md` — agent workflow and workspace snapshot procedure
