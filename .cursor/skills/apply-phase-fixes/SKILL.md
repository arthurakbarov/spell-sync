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
8. Run `python3 scripts/run_pre_final_checks.py` before commits.
9. Set phase status to `awaiting-approval`; create corrective local commit(s). Do not push.
10. Verify clean working trees (`git status --short`).
11. Run `scripts/ci.sh` **once** on the committed HEAD (final evidence).
12. Verify `python3 scripts/check-ci-evidence.py` (`CI_EVIDENCE_RESULT=success`).
13. On CI failure after commit: fix; focused failed-check validation; new corrective commit;
    clean tree; new full CI. Do not amend if a new commit preserves evidence more clearly.
14. Leave current phase at `awaiting-approval`.
15. Return a defect-by-defect report and stop.

## Validation

Use `select-and-run-tests` during the fix loop. Use `spell-sync-ci` only for final full CI
diagnosis. Do not run full CI after each individual defect.

## Finalize workspace snapshot

Modifying tasks only — after successful `python3 scripts/check-ci-evidence.py`: skill
`create-code-snapshot` in spell-sync-dev with `--force`, then `--check`; re-verify evidence
and clean trees; canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
