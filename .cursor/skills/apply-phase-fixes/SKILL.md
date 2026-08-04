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
7. After all defects in a cluster are fixed, run `select-and-run-tests` / `run_dev_loop.py`
   once for the combined affected clusters — not after every single defect.
8. Set phase status to `awaiting-approval`; create corrective local commit(s). Do not push.
9. Run L1: `python3 scripts/run_dev_loop.py --commit-gate`.
10. Verify clean working trees (`git status --short`).
11. Assess local necessity: `python3 scripts/check_ci_necessity.py --purpose local --explain`.
12. When `commit-gate-sufficient` / `lightweight-sufficient` / `no-action`: do **not** run full CI.
13. Run L2 (`scripts/ci.sh` + `check_ci_evidence.py`) only for `--purpose publish` or owner final.
14. Leave current phase at `awaiting-approval`.
15. Return a defect-by-defect report and stop.

## Validation

Use `select-and-run-tests` / `run_dev_loop.py` during the fix loop. Use `spell-sync-ci` L2
only for publish/final. Do not run full CI after each individual defect.

## Finalize workspace snapshot

Modifying tasks — after L1 (`run_dev_loop.py --commit-gate`). When L2 ran, require
`python3 scripts/check_ci_evidence.py` success first.
Skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
