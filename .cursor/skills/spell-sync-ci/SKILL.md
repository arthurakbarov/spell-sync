---
name: spell-sync-ci
description: >-
  Validate spell-sync changes. Default is local minimal (edit + commit gate). Full scripts/ci.sh
  runs only for --purpose publish (push/release) or explicit owner final request.
---

# spell-sync CI

## When to use

- During modifying tasks: local minimal only
- Before push / tag / release / explicit “final”: full CI on committed HEAD
- To rerun a **single failed full CI gate** while fixing

## Do not use

- To run full CI after every polish commit
- As a substitute for reading failing test output and fixing root causes
- To add meaningless tests solely to hit coverage lines
- To repeat full CI without file changes after a failure

## Local workflow (default)

0. Environment:

```bash
python3 scripts/project_environment.py check
```

1. Local minimal via skill `select-and-run-tests` / `run_dev_loop.py`
   (strict budgets: edit ≤60s, commit gate ≤120s; report `DEV_LOOP_BUDGET_*`).
2. Commit tracked changes; verify clean working tree.
3. Assess **local** necessity:

```bash
python3 scripts/check_ci_necessity.py --purpose local --explain
```

4. When `commit-gate-sufficient`: stop (no full CI).
5. When `lightweight-sufficient`:

```bash
python3 scripts/run_lightweight_validation.py
```

6. When `no-action`: skip redundant validation.

## Publish / final workflow (full CI only)

Use when the owner requests push, tag, release, or explicit final validation:

```bash
python3 scripts/check_ci_necessity.py --purpose publish --explain
scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

Full CI hard safety wall **≤1200s (20 min)**. Compare planned expected/soft vs actual wall
(`EXECUTION_*` / CI summary timing). Report status
`within-expected` | `soft-exceeded` | `hard-bound` if the safety hard cap fired.
Do not fail full CI solely for exceeding expected — only for functional/safety failure or
hard-cap termination.

Do not pipe CI through `tail`, `tee`, or other wrappers.

Release / signed artifacts:

```bash
python3 scripts/check_ci_evidence.py --release
```

On full CI failure, fix and rerun only the failed check:

```bash
scripts/ci.sh --only ruff.format
```

Then commit, clean tree, reassess with `--purpose publish`, and run one new full CI when required.

Diagnostic modes (`--only`, `--from`, `--resume-failed`) do **not** count as publish
evidence. Only `mode=full` with `finalEvidence=true` and `CI_EVIDENCE_RESULT=success`
count for publish evidence.

## What ci.sh enforces (full CI)

`scripts/ci.sh` is the single full-CI entry point. List checks with:

```bash
scripts/ci.sh --list-checks
```

Includes docs/agent/architecture validators, ruff, mypy, grouped pytest **with coverage**,
packaging, wheel-smoke, and smokes.

## Related

- Strategy: `docs/TESTING_STRATEGY.md`
- Skill: `select-and-run-tests`, `release-candidate`
- Necessity: `scripts/check_ci_necessity.py --purpose local|publish`

## Finalize workspace snapshot

Modifying tasks — after commit gate (`run_dev_loop.py --commit-gate`) and local necessity.
When this skill ran full CI, require `python3 scripts/check_ci_evidence.py` success first.
Then skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
