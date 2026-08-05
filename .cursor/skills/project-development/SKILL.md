---
name: project-development
description: >-
  Project standards and phrase map for spell-sync. Use when starting work,
  asking how to develop safely here, or phrases продолжи / делай всё /
  чистый репо (also skill autonomous-work).
---

# Project development (spell-sync)

Shared contract: `.cursor/README.md` § Shared contract.

Always-on: `project-development.mdc`, `agent-workflow.mdc`, `test-efficiency.mdc`,
`execution-time-control.mdc`, `project-environment.mdc`.

## When to use

- Starting work in this repository
- Asking how to develop safely here
- Phrases продолжи / делай всё / чистый репо (with skill `autonomous-work`)

## Do not use

- To bypass mutation-safety or architecture phase skills for those change types
- To run full CI when local necessity is commit-gate-sufficient

## Loop (edit)

1. `python3 scripts/agent_context.py`
2. `python3 scripts/project_environment.py check`
3. Minimal coherent diff
4. `python3 scripts/run_dev_loop.py` (or `--plan` first)

Operator SSOT: `docs/WORKFLOW.md`.

## Checkpoint

```bash
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_ci_necessity.py --purpose local --explain
```

Local commits anytime (no owner approval).

## Full gate (owner push / publish / final only)

```bash
python3 scripts/preflight_publish.py
# owner-approved execute:
python3 scripts/preflight_publish.py --execute
```

Or `scripts/ci.sh` then `python3 scripts/check_ci_evidence.py`.

## Phrase map

| Phrase | Action |
|--------|--------|
| продолжи | Continue arc; `run_dev_loop.py`; no full CI |
| делай всё | Complete goal; full CI only for publish/final |
| проверь историю | Audit history / dead refs; report first |
| чистый репо | Docs/stale cleanup; no git rewrite |

## Related

- Skill `repository-workflow` — inspect → edit → checkpoint → gate
- Skill `preflight-publish` — publish readiness
- Skill `git-change-management` / `security-audit` — git + privacy
- Honesty: `docs/CONTRACTS.md`, `docs/FEATURE_MATRIX.md`, `docs/INVENTORY.md`
- Command SSOT: `config/dev-commands.json` + `config/dev-surface.json`
- Done: `docs/ENGINEERING_COMPLETION.md` + `docs/PRODUCT_COMPLETION.md`
- Operator loop: `docs/WORKFLOW.md`
- Artifacts: `docs/ARTIFACTS-AND-STATE.md`
- Triage: `python3 scripts/dev_runs.py failures`
