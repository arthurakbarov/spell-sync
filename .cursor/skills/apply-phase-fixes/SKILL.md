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

1. Reproduce each listed defect.
2. Add a regression test per defect.
3. Apply the minimal fix.
4. Do not refactor unrelated code.
5. Do not start the next phase.
6. Update docs/ADR only when factual contracts change.
7. Run focused validation for touched scope.
8. Run `scripts/ci.sh`.
9. Create a corrective local commit.
10. Leave current phase at `awaiting-approval`.
11. Return a defect-by-defect report and stop.

## Per-defect report

For each defect include:

- reproduction steps
- root cause
- fix summary
- regression test path
- validation result (command + exit code)

## Validation

Follow `spell-sync-ci` for CI diagnosis. Use stable test/check IDs in the report.

## Finalize workspace snapshot

When this task changed workspace state in any repository:

1. Compare final Git metadata to the baseline captured at task start.
2. Follow skill `create-code-snapshot` in the private maintainer repository (`spell-sync-dev`).
3. Do not finish the success report until `$HOME/code.zip` is validated when recreation was required.
4. Include the **Workspace snapshot** section in the final report.
