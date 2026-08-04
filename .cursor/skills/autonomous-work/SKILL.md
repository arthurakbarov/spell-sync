---
name: autonomous-work
description: >-
  Autonomous engineering on spell-sync when the user says continue or do
  everything. Use for продолжи, делай всё, проверь историю, чистый репо, or
  open-ended improvement requests on this repository.
---

# Autonomous work (spell-sync)

Shared contract: `.cursor/README.md` § Shared contract. Base: skill
`project-development`. Loop: `agent-workflow` + `select-and-run-tests`.

## When to use

- Owner says продолжи, делай всё, проверь историю, or чистый репо
- Open-ended continue on the current arc without a new phase assignment

## Do not use

- To start the next architecture phase without owner approval
- To push, tag, or publish without an explicit owner request
- As a substitute for `execute-current-phase` on a named roadmap phase

## Loop (edit)

1. `python3 scripts/agent_context.py`
2. `python3 scripts/project_environment.py check`
3. Small focused diffs; local commits anytime (any branch)
4. `python3 scripts/run_dev_loop.py` (≤60s; prints `eta:` when display >5s)

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

Then workspace snapshot for modifying tasks (`docs/AGENT_DEVELOPMENT.md`).

## Phrase map

| Phrase | Meaning |
|--------|---------|
| продолжи | Continue arc; local minimal only; no full CI |
| делай всё | End-to-end; full CI only if publish/final in scope |
| проверь историю | Inspect history / dead refs; report before destructive cleanup |
| чистый репо | Slim stale docs/refs; no git rewrite unless secrets |

## Related

- Do not run full `scripts/ci.sh` after every «продолжи» batch
- Do not hide work in persistent `git stash`
- Do not pipe CI through `tail` / `tee`
- Interactive prompts: +5s each on ETA display only (`prompt_user` / `--prompts N`)
