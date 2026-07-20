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

- `git status --short` must be clean before starting
- run `python3 scripts/check-agent-config.py`
- run `python3 scripts/check-docs-contract.py`
- run `scripts/ci.sh` when baseline is uncertain
- stop with a prerequisite report if tree is dirty or baseline CI fails

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

After logical chunks:

- focused pytest for changed scope
- architecture tests (`tests/test_application_requests.py`, phase-specific guards)
- `python3 -m ruff check spell_sync tests scripts`
- `python3 -m mypy spell_sync` when types changed
- `git diff --check`

## Step 7 — update repository knowledge

Update in the same task when facts change:

- architecture tracker (phase section, status block)
- canonical architecture docs and ADRs
- agent rules/skills only when workflow or boundaries change
- tests and documentation contracts

## Step 8 — full validation

```bash
scripts/ci.sh
```

Read `CI_RESULT`, `CI_EXIT`, `CI_SUMMARY`, `CI_LOG`, and `CI_FAILED_ID` on failure.
Fix phase-related failures and rerun. Do not ask the owner to read raw logs.

## Step 9 — commit

After green CI:

- review diff and scope
- create one logical local commit (or a short sequence if clearly separated)
- do not push

## Step 10 — awaiting approval

Set current phase status to `awaiting-approval` in the architecture status block.
Keep `current` on this phase. Do not set `complete` or advance `current`.

If the status update requires a docs-only follow-up, commit it locally and rerun lightweight validators.

## Step 11 — report and stop

Return the final report contract from `docs/AGENT_DEVELOPMENT.md`. Stop. Do not start the next phase.
