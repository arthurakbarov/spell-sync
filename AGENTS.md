# spell-sync — agent guide

Public repository for Spell Sync: a CLI and TUI tool that keeps one **canonical personal
wordlist** synchronized with **application custom dictionaries**. Built-in application
dictionaries are never inspected or modified.

Development is **agent-first**: implement changes, run tests, interpret CI output, and update
docs/contracts. See `docs/AGENT_DEVELOPMENT.md`.

## Architecture map

```text
CLI (CliOptions) → cli_request_adapter → typed application requests
TUI controller   → typed application requests
  → SpellSyncService (thin facade)
  → application/services/* (Diagnostics, Inspection, Sync, Recovery, Setup, TargetSettings)
  → RuntimeResolver → ResolvedRuntime / RuntimeIdentity
  → core (sync_run, push_*, project_setup, diagnostics)
```

- **Typed requests:** immutable DTOs in `application/requests.py`; no `CliOptions` outside CLI
- **Explicit runtime:** `RuntimeResolver`; no production `ContextVar` for settings or validated runtime
- **Thin facade:** `SpellSyncService` delegates to focused services under `application/services/`
- **Structured diagnostics:** typed `EventId` / `TechnicalEvent`; JSON Lines technical log; presentation at CLI/TUI only
- **Architecture guards:** `scripts/check_architecture.py` (`architecture.boundaries` in CI)

## CLI commands (12)

```text agent-config-cli-commands
`config-check`, `doctor`, `init`, `lint`, `plan`, `pull`, `push`, `recover`, `status`, `support-report`, `ui`, `version`
```

No-args on a TTY launches the TUI when a project is ready. See `spell_sync/cli.py`.

Canonical references:

```text agent-config-paths
docs/README.md
docs/ARCHITECTURE.md
docs/architecture/APPLICATION_LAYER.md
docs/architecture/RUNTIME_CONTEXT.md
docs/architecture/MUTATION_SAFETY.md
docs/architecture/DIAGNOSTICS.md
docs/PROJECT_MAP.md
docs/RECOVERY.md
docs/TUI_IMPLEMENTATION.md
docs/CONFIGURATION.md
docs/AGENT_DEVELOPMENT.md
```

## Pull and Push

- **Pull:** application custom dictionaries → canonical personal wordlist (`W' = W ∪ C₁ ∪ … ∪ Cₙ`)
- **Push:** canonical personal wordlist → application custom dictionaries
- Most targets receive the full wordlist; some platform-specific targets receive an applicable
  subset (`win-en`, `win-en-gb`, `win-ru`)

Central product copy lives in `spell_sync/application/product_concepts.py`.

## Critical commands

```bash
python3 scripts/agent_context.py
python3 scripts/test_plan.py --dev-scope
python3 scripts/run_dev_loop.py
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_architecture.py --check
python3 scripts/check_docs_contract.py
python3 scripts/check_agent_config.py
python3 scripts/check_ci_necessity.py --purpose local --explain
# Full CI only before push/release:
python3 scripts/check_ci_necessity.py --purpose publish --explain
scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

`scripts/ci.sh` is the single **full CI / publish** entry point. Ordinary edit/commit cycles
use local minimal (`run_dev_loop.py`, 60s edit / 120s commit gate) and must not run full CI when
necessity is `commit-gate-sufficient`. On full CI completion it prints `CI_RESULT`, `CI_EXIT`,
`CI_SUMMARY`, and `CI_LOG`. See `docs/TESTING_STRATEGY.md`.

Docs style, docs contract, agent config, architecture boundaries, ruff, mypy, grouped pytest
with **100% line** and **≥96% branch** coverage on `spell_sync/` (full CI only), packaging,
installed-wheel smoke, and headless command scenarios.

Requires **Python 3.11+** (`pyproject.toml`).

## Critical prohibitions

- TUI must not call low-level dictionary writers, journal writers, or config writers directly
- TUI must not invoke CLI via subprocess — use `SpellSyncService`
- Application and TUI must not import `CliOptions`, argparse, or Textual from core paths
- No hidden runtime `ContextVar` or module-level config cache in production paths
- No mutation without project operation lock
- No execution from a stale preview or mismatched plan/update ID
- Pending Recovery blocks new write operations
- No automatic Pull, Push, or Recovery
- User words must not appear in operation history or technical logs
- Tests use synthetic dictionaries and temporary HOME only — never real application dictionaries
- No push, tag, release, or package publish without explicit owner request
- No private user data, maintainer paths, or personal wordlists in public commits

Local `git commit` on any branch does **not** require owner approval (see rule
`git-change-management`).

## Cursor configuration

```text
.cursor/rules/     short invariants and file-scoped guidance
.cursor/skills/    procedural workflows (CI, phases, safety audit, TUI, packaging)
```

Phase-driven workflow skills (use these for architecture roadmap work):

- `execute-current-phase` — implement and validate the current architecture phase
- `apply-phase-fixes` — correct owner-listed defects without advancing the roadmap
- `advance-current-phase` — mark an approved phase complete (owner command only)
- `architecture-refactor` — architecture migration with safety and guard updates
- `diagnostics-change` — structured events, logging, and privacy changes

Other skills:

- `autonomous-work` — продолжи / делай всё / open-ended continue without over-CI
- `project-development` — phrase map and day-to-day development standards
- `repository-workflow` — inspect → edit loop → commit gate → publish order
- `git-change-management` — local commits anytime; push/tag/publish owner-gated
- `security-audit` — privacy scan before share or owner-requested push
- `spell-sync-ci` — local minimal locally; full CI only for publish/release
- `select-and-run-tests` — affected module plan via `run_dev_loop.py`
- `run-time-controlled-command` — run registered expensive commands under budget control
- `mutation-safety-audit` — audit Pull/Push/Recovery/lock/journal mutation invariants
- `tui-flow` — add or change TUI screens, navigation, and related tests
- `add-target` — add a new application custom-dictionary target
- `platform-validation` — record real-application validation on a specific OS
- `installed-wheel-smoke` — verify an installed wheel outside the source checkout
- `release-candidate` — prepare a release candidate without publishing
- `privacy-export` — scan artifacts and repo content before publication or sharing
- `project-environment` — bootstrap/sync/check maintainer Python environment lifecycle

See also `.cursor/README.md` for shared vs project-specific agent contracts.

Architecture tracker: `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md` (`[architecture-status:start]` block).

Engineering rules and skills are self-contained in this repository. Maintainer topology and
publication workflows live only in the private maintainer workspace (not shipped here).

## Agent prohibitions

- Do not start the next architecture phase without owner approval
- Do not mark a phase `complete` from implementation work — use `awaiting-approval`, then `advance-current-phase`
- Do not create handoff or upload archive workflows (see **Workspace snapshot**)

## Workspace snapshot

Modifying tasks finalize per `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot before the final report.

## Testing focus

| Area | Typical tests |
|------|---------------|
| Architecture | `tests/test_check_architecture.py`, `tests/tui/test_architecture.py` |
| TUI | `tests/tui/`, fake service for UI; real core for safety integration |
| Pull/Push safety | `tests/test_pull_safety.py`, `tests/test_transaction_safety.py` |
| TUI mutation | `tests/test_tui_mutation_safety.py`, `tests/test_tui_recovery_safety.py` |
| Diagnostics | `tests/test_technical_logging.py`, `tests/test_diagnostic_redaction.py` |
| Target settings | `tests/test_target_settings.py` |
| Installed wheel | `tests/test_installed_workflow.py` |

Prefer local minimal (`python3 scripts/run_dev_loop.py`) first, then
`python3 scripts/check_ci_necessity.py --purpose local`. Full CI only for
`--purpose publish` / push / release.

Execution time control bounds full CI and registered expensive commands through
`scripts/execution_control/`. Product Pull/Push/Recovery paths are not wrapped. See
`docs/EXECUTION_TIME_CONTROL.md`.

Full CI evidence binds to CI-relevant inputs for **publish** workflows. Ordinary polish
tasks may finish with commit gate only when necessity is `commit-gate-sufficient`. Exact Git HEAD
matching remains required for release, publication, and signed artifact workflows.
