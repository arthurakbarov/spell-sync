---
name: execute-current-phase
description: Implement only the current architecture phase, validate it completely, commit it locally, and stop for approval.
---

# Execute current phase

## When to use

- Owner or tracker assigns work on the current architecture phase
- Starting implementation after bootstrap or after `advance-current-phase`

## Do not use

- To fix defects after review — use `apply-phase-fixes`
- To mark a phase complete — use `advance-current-phase`
- To run CI only — use `spell-sync-ci`
- To begin the next phase without owner approval

## Step 1 — load context

Read:

- `AGENTS.md`
- `docs/AGENT_DEVELOPMENT.md`
- applicable `.cursor/rules/**`
- `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md` (current phase + status block)
- related ADRs under `docs/decisions/`
- affected source, tests, and contracts

## Step 2 — verify baseline

- `git status --short` must be clean before starting a **new phase implementation**
- run `python3 scripts/check_agent_config.py`
- run `python3 scripts/check_docs_contract.py`
- reuse existing publish CI evidence when available; do **not** start with full CI
- use L0/L1 via skill `select-and-run-tests` / `run_dev_loop.py`

## Step 3 — start phase

Read `[architecture-status:start]` … `[architecture-status:end]`.

| Current status | Action |
|----------------|--------|
| `not-started` | Set to `in-progress`; do not change completed predecessors |
| `in-progress` | Continue implementation |
| `blocked` | Stop; report blocker |
| `awaiting-approval` | Do not implement; wait for owner or use `apply-phase-fixes` |
| `complete` | Invalid for `current`; stop |

## Step 4 — factual inventory

Before edits, record:

- current implementation
- dependency paths
- affected contracts and tests
- safety risks
- deferred work for later phases

## Step 5 — implement only current phase

- Do not start the next phase
- Minimal coherent diff; no speculative abstractions
- No parallel APIs or unused types
- Preserve backward compatibility unless the phase explicitly changes contracts
- For architecture phases, also follow `architecture-refactor`
- For mutation paths, run `mutation-safety-audit` before declaring done

## Step 6 — validate incrementally

After logical chunks use skill `select-and-run-tests` (L0). Do not run full CI
during the edit loop.

- `python3 scripts/run_dev_loop.py`
- architecture check when application boundaries change
- `git diff --check`

## Step 7 — update repository knowledge

Update in the same task when facts change:

- architecture tracker (phase section, status block)
- canonical architecture docs and ADRs
- agent rules/skills only when workflow or boundaries change
- tests and documentation contracts

## Step 8 — commit and L1

Set current phase status to `awaiting-approval` in the architecture status block.
Create one logical local commit (or a short sequence if clearly separated). Do not push.

```bash
python3 scripts/run_dev_loop.py --commit-gate
```

Pre-final polish (`run_pre_final_checks.py`) is optional for local work; it is not required
before every commit.

## Step 9 — clean verification

`git status --short` must be clean in every affected repository.

## Step 10 — local necessity (not full CI)

```bash
python3 scripts/check_ci_necessity.py --purpose local --explain
```

When `commit-gate-sufficient` / `lightweight-sufficient` / `no-action`: do **not** run
`scripts/ci.sh`. Run lightweight validation only when `lightweight-sufficient`.

## Step 11 — L2 only on owner publish/final request

Full CI is not part of ordinary phase completion. When the owner explicitly requests
push/release/final, run L2 on committed HEAD:

```bash
python3 scripts/check_ci_necessity.py --purpose publish --explain
scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

## Step 12 — report and stop

Return the final report contract from `docs/AGENT_DEVELOPMENT.md`. Stop. Do not start the next phase.

## Finalize workspace snapshot

Modifying tasks — after L1 success (`run_dev_loop.py --commit-gate` / purpose local).
When L2 ran, also require `python3 scripts/check_ci_evidence.py` success first.
Then skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
