---
name: apply-phase-fixes
description: Correct explicit defects found in the current awaiting-approval phase without broadening scope or advancing the architecture roadmap.
---

# Apply phase fixes

## When to use

- Owner lists concrete defects after reviewing a phase in `awaiting-approval`
- Corrective work before approval or before `advance-current-phase`

## Do not use

- To implement a new phase
- To broaden scope beyond listed defects
- To mark a phase complete

## Prerequisites

Current phase status must be `awaiting-approval` or `in-progress`.
Working tree should be clean before starting.

## Workflow

1. Reproduce each listed defect (Level 0 exact test).
2. Add a regression test per defect.
3. Apply the minimal fix.
4. Do not refactor unrelated code.
5. Do not start the next phase.
6. Update docs/ADR only when factual contracts change.
7. After all defects in a cluster are fixed, run `select-and-run-tests` once for the
   combined affected clusters — not after every single defect.
8. Run `scripts/ci.sh` **once** after all defects are fixed.
9. Create a corrective local commit.
10. Leave current phase at `awaiting-approval`.
11. Return a defect-by-defect report and stop.

## Validation

Use `select-and-run-tests` during the fix loop. Use `spell-sync-ci` only for final full CI
diagnosis. Do not run full CI after each individual defect.

## Finalize workspace snapshot

Before the final user report on modifying tasks:

1. Remove stale non-canonical archives (script default cleanup).
2. Run skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`.
3. Canonical paths: `$HOME/code.zip` and `$HOME/code.zip.sha256` only.
4. Include **Workspace snapshot** in the report and end with `CODE_ARCHIVE` / `SHA256`.
