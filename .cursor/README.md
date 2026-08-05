# Cursor rules & skills (spell-sync)

Project-specific agent guidance. Human entry: [`AGENTS.md`](../AGENTS.md),
workflow: [`docs/AGENT_DEVELOPMENT.md`](../docs/AGENT_DEVELOPMENT.md).

## Shared contract (with nix-darwin)

Same **skill/rule names** and the same **skeleton** as nix-darwin-config. Bodies use
only local commands. Product/flake specifics stay in separate rules and are listed below.

### Shared skill skeleton

```text
When to use
Do not use
Loop (edit)          - smallest local check
Checkpoint           - commit-boundary validation
Full gate            - only owner push / publish / final
Related              - optional cross-links
```

| Shared name | spell-sync body | nix-darwin body |
|-------------|-----------------|-----------------|
| `agent-workflow` | `run_dev_loop` / commit-gate / `ci.sh` | `nx check` / `--changed` / nx full gate |
| `test-efficiency` | local minimal vs publish CI | sample/fast vs nx full gate |
| `execution-time-control` | `execution_control/` + ETA | `nx run-budget` + ETA |
| `select-and-run-tests` | `test_plan` + `run_dev_loop` | `nx affected` + `nx check` |
| `repository-workflow` | inspect → loop → gate | `nx inspect/affected` → loop → gate |
| `git-change-management` | local commits anytime; push owner-gated | **no commits on `main`**; commit when asked |
| `autonomous-work` / `project-development` | phrase map + loop | phrase map + `nx` loop |
| `project-development` rule | thin always-on invariants | thin always-on invariants |
| `run-time-controlled-command` | `run_with_budget.py` | `nx run-budget` |
| `security-audit` | `privacy-export` + checks | `nx audit-secrets` / history |
| `project-environment` | `project_environment.py` | `nx env` / uv |
| `agent-context` inspect | `scripts/agent_context.py` | `nx agent-context` |
| `comments` hygiene | rule `comments.mdc` | rule `comments.mdc` |
| after-changes ladder | rule `after-changes.mdc` | same ladder; nix rule filename keeps a check- prefix |
| `preflight-publish` | `preflight_publish.py` (+ privacy) | `nx preflight-push` / audit-history |

Naming note: spell-sync uses `after-changes.mdc` so agent-config hygiene does not treat the
rule name as a forbidden hyphenated check- script alias. Same role as the nix rule.

Intentional divergence: **local commits without operator approval** are allowed here; nix
keeps feature-branch + explicit-commit policy.

## Always-on rules

| Rule | Role |
|------|------|
| `project-development.mdc` | Thin invariants, surfaces, ASCII harness CLI |
| `agent-workflow.mdc` | Deterministic edit loop |
| `test-efficiency.mdc` | Local minimal vs full CI only on publish/final |
| `execution-time-control.mdc` | Budgets, stalls, ETA, no unbounded gates |
| `project-environment.mdc` | Python / uv / env contract |
| `project-safety.mdc` | Mutation + release/privacy invariants |
| `git-change-management.mdc` | Local commits anytime; push/tag/publish owner-gated; SSOT `docs/GIT-WORKFLOW.md` |
| `karpathy-guidelines.mdc` | Simplicity / surgical diffs |
| `no-canvas-for-text.mdc` | Never use Canvas for text/tables — reply in chat |

## On-edit rules (globs)

| Rule | When |
|------|------|
| `after-changes.mdc` | scripts, product, docs, tests - validation ladder |
| `comments.mdc` | Python / shell / TOML comment style |
| `architecture-boundaries.mdc` | application / CLI / TUI boundaries |
| `tests-fixtures.mdc` | pytest fixtures / synthetic HOME |
| `tui.mdc` | Textual product TUI |
| `product-language.mdc` | User-facing product copy |
| `packaging-privacy.mdc` | Wheel / package privacy |

## Shared skills

| Skill | When |
|-------|------|
| `select-and-run-tests` | Smallest local validation; defer full CI |
| `run-time-controlled-command` | Budgeted expensive commands |
| `autonomous-work` | продолжи / делай всё / open-ended continue |
| `project-development` | Standards + phrase map |
| `repository-workflow` | Cross-cutting change arc |
| `git-change-management` | Local commits anytime; push owner-gated |
| `security-audit` | Privacy scan before share/push |
| `preflight-publish` | Publish gate: necessity → CI → evidence → privacy |
| `project-environment` | `.venv` / uv lifecycle |

## spell-sync specific (not shared)

| Skill / area | Why project-specific |
|--------------|----------------------|
| `execute-current-phase` / `apply-phase-fixes` / `advance-current-phase` | Architecture roadmap phases |
| `architecture-refactor` | Layered Python app migration |
| `diagnostics-change` | Structured EventId / technical log |
| `mutation-safety-audit` | Pull / Push / Recovery / lock |
| `tui-flow` | Textual product TUI (not owner nx menu) |
| `add-target` / `platform-validation` | Application dictionary targets |
| `spell-sync-ci` / `release-candidate` / `installed-wheel-smoke` | Publish CI + packaging |
| `privacy-export` | Public artifact scan (pairs with `security-audit`) |
| `project-safety` / packaging-privacy / product-language | Product invariants (rules) |
| Workspace snapshot | Three-repo maintainer topology via spell-sync-dev |

## Surfaces

- Inspect: `python3 scripts/agent_context.py` (optional `--json`)
- Session reuse: `python3 scripts/check_session.py` (start / record / lookup / finish)
- Edit loop: `python3 scripts/run_dev_loop.py` (≤60s)
- Checkpoint: `python3 scripts/run_dev_loop.py --commit-gate` (≤120s)
- Full CI: `scripts/ci.sh` only on owner push / publish / final
- Triage: `python3 scripts/dev_runs.py failures` / `show <run-id>`
- Command SSOT: `config/dev-commands.json` + `config/dev-surface.json`
- Done-definition: `docs/ENGINEERING_COMPLETION.md` + `docs/PRODUCT_COMPLETION.md`
