# spell-sync — agent guide

Public repository for Spell Sync: a CLI and TUI tool that keeps one **canonical personal
wordlist** synchronized with **application custom dictionaries**. Built-in application
dictionaries are never inspected or modified.

Development is **agent-first**: the Cursor Agent implements changes, runs tests, interprets
CI logs, and updates docs/contracts. The repository owner defines intent, approves scope,
and decides release policy. See `docs/AGENT_DEVELOPMENT.md`.

## Architecture map

```text
CLI parser (CliOptions) / TUI controller
    ↓
CLI adapter / direct request builders
    ↓
immutable application requests (application/requests.py)
    ↓
SpellSyncService (application/service.py)
    ↓
core planning and execution (sync_run, push_prepared, push_transaction, pull)
    ↓
filesystem adapters (dictionaries, io, paths)
```

CLI/TUI adapters create immutable application requests. The application layer does not
depend on `CliOptions`. Mutation CLI commands route through `SpellSyncService`; `config-check`
and `lint` are CLI utilities. Runtime settings are still implicit in 0.2.1 (ContextVar);
explicit runtime is Phase 3.

Canonical references:

- `docs/ARCHITECTURE.md` — wordlist model, Pull/Push semantics, module map
- `docs/TUI_IMPLEMENTATION.md` — Textual screens, controller, workers
- `docs/RECOVERY.md` — journal, snapshots, recovery invariants
- `docs/CONFIGURATION.md` — spell-sync.toml schema

## Pull and Push

- **Pull:** application custom dictionaries → canonical personal wordlist (`W' = W ∪ C₁ ∪ … ∪ Cₙ`)
- **Push:** canonical personal wordlist → application custom dictionaries
- Most targets receive the full wordlist; some platform-specific targets receive an applicable
  subset (`win-en`, `win-en-gb`, `win-ru`)

Central product copy lives in `spell_sync/application/product_concepts.py`.

## CLI commands (12)

```text agent-config-cli-commands
`config-check`, `doctor`, `init`, `lint`, `plan`, `pull`, `push`, `recover`, `status`, `support-report`, `ui`, `version`
```

No-args on a TTY launches the TUI when a project is ready. See `spell_sync/cli.py`.

## Critical commands

```bash
python3.11 -m ruff check spell_sync tests
python3.11 -m ruff format --check spell_sync tests
python3.11 -m mypy spell_sync
python3.11 -m pytest <focused tests> -q
scripts/ci.sh
python3.11 scripts/check-agent-config.py
python3.11 scripts/check-docs-contract.py
```

`scripts/ci.sh` is the single CI entry point. On completion it prints `CI_RESULT`, `CI_EXIT`,
`CI_SUMMARY`, and `CI_LOG` (full log under `.artifacts/ci/`). The Cursor Agent reads those
paths; the owner is not expected to tail logs manually. Architecture and documentation
contracts are mandatory before declaring a task complete.

Docs style, docs contract, ruff, mypy, pytest with **100% line** and **≥96% branch**
coverage on `spell_sync/`, wheel build, twine check, lint smoke, headless command scenarios.

Requires **Python 3.11+** (`pyproject.toml`).

## Critical prohibitions

- TUI must not call low-level dictionary writers, journal writers, or config writers directly
- TUI must not invoke CLI via subprocess — use `SpellSyncService`
- No mutation without project operation lock
- No execution from a stale preview or mismatched plan/update ID
- Pending Recovery blocks new write operations
- No automatic Pull, Push, or Recovery
- User words must not appear in operation history or technical logs
- Tests use synthetic dictionaries and temporary HOME only — never real application dictionaries
- No push, tag, release, or package publish without explicit owner request
- No private user data, maintainer paths, or personal wordlists in public commits

## Cursor configuration

Project-specific agent context for contributors:

```text
.cursor/rules/     short invariants and file-scoped guidance
.cursor/skills/    procedural workflows (CI, safety audit, TUI, packaging)
```

Open this repository alone — engineering rules and skills are self-contained here. Maintainer
topology, remotes, and publication workflows live only in the private maintainer workspace
(not shipped with this repository).

## Testing focus

| Area | Typical tests |
|------|---------------|
| TUI | `tests/tui/`, fake service for UI; real core for safety integration |
| Pull/Push safety | `tests/test_pull_safety.py`, `tests/test_transaction_safety.py` |
| TUI mutation | `tests/test_tui_mutation_safety.py`, `tests/test_tui_recovery_safety.py` |
| Target settings | `tests/test_target_settings.py` |
| Review workflow | `tests/test_review_workflow.py`, `tests/tui/test_review_workflow.py` |
| Installed wheel | `tests/test_installed_workflow.py` |
| Architecture | `tests/tui/test_architecture.py` |

Prefer focused tests first, then full `scripts/ci.sh`.
