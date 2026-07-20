---
name: advance-current-phase
description: Mark an explicitly approved phase complete and make the next planned phase current without implementing it.
---

# Advance current phase

## When to use

- Owner explicitly accepts the current phase (for example: "current phase accepted")
- Immediately after approval, before starting new implementation

## Do not use

- Without explicit owner approval
- To implement the next phase (use `execute-current-phase` after this skill)
- When working tree is dirty or CI is red

## Prerequisites

- Current phase status is `awaiting-approval`
- Clean working tree
- Implementation commit(s) for the phase exist locally
- Full CI was green when the phase entered `awaiting-approval`

## Workflow

1. Confirm owner approval in the session request.
2. Verify clean tree: `git status --short`
3. Run lightweight validators:
   - `python3 scripts/check-agent-config.py`
   - `python3 scripts/check-docs-contract.py`
4. In `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md`:
   - set current phase: `awaiting-approval` → `complete`
   - set next planned phase: `current` and `not-started`
5. Do not change production code.
6. Create a docs-only local commit.
7. Stop. Do not run `execute-current-phase` automatically.

## Status rules

- Exactly one `current` field
- `current` must not point to `complete`
- At most one `in-progress` and one `awaiting-approval` across all phases
