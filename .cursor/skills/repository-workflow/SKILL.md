---
name: repository-workflow
description: >-
  Agent change-arc workflow for spell-sync. Use for architectural or
  cross-cutting work, or when choosing inspect → edit loop → commit gate →
  publish CI order.
---

# Repository workflow (spell-sync)

Shared contract: `.cursor/README.md` § Shared contract.

Rules: `agent-workflow.mdc`, `after-changes.mdc`, `git-change-management.mdc`.
Skills: `select-and-run-tests`, `spell-sync-ci`, `security-audit`.
SSOT: `docs/AGENT_DEVELOPMENT.md`.

## When to use

- Cross-cutting or multi-area changes
- Open-ended engineering arcs (with `autonomous-work`)
- Clarifying validation order before implementation

## Do not use

- To advance architecture phases — use `advance-current-phase` after owner approval
- To replace `execute-current-phase` on a named roadmap phase
- To run full CI during ordinary polish

## Loop (edit)

1. `python3 scripts/agent_context.py` (optional `--json`) — branch, dirty, necessity, suggested runner
2. `python3 scripts/test_plan.py --dev-scope --explain`
3. Smallest correct diff; local commits anytime.
4. `python3 scripts/run_dev_loop.py` (≤60s)

## Checkpoint

```bash
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_ci_necessity.py --purpose local --explain
```

## Full gate (owner push / publish / final only)

```bash
scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

Then workspace snapshot for modifying tasks.

## Command map

| Command | Role |
|---------|------|
| `python3 scripts/agent_context.py` | Inspect rollup |
| `python3 scripts/project_environment.py check` | Env |
| `python3 scripts/test_plan.py --dev-scope --explain` | Scope |
| `python3 scripts/run_dev_loop.py` | Edit loop |
| `python3 scripts/run_dev_loop.py --commit-gate` | Checkpoint |
| `python3 scripts/check_ci_necessity.py --purpose local --explain` | Necessity |
| `scripts/ci.sh` | Owner publish CI |
| `python3 scripts/dev_runs.py failures` | Triage |

## Related

- Architecture roadmap: `execute-current-phase` / `apply-phase-fixes`
- Do not chain checkpoint + full CI in one shell line on «продолжи»
