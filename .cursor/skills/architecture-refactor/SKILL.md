---
name: architecture-refactor
description: Perform an architecture migration while preserving safety contracts, dependency direction, tests, ADRs, and one canonical execution path.
---

# Architecture refactor

## When to use

- `execute-current-phase` targets an architecture migration phase
- Dependency direction, runtime model, or service boundaries change

## Do not use

- For product-only bug fixes outside architecture scope
- To introduce a parallel execution path "for convenience"

## Required steps

1. **Dependency inventory** — map imports before and after; no reverse dependencies.
2. **Safety inventory** — list Pull/Push/Recovery/lock/journal invariants at risk.
3. **Migration order** — follow the tracker; finish one layer before the next.
4. **Single path** — remove or migrate callers; no permanent compatibility wrappers.
5. **No hidden globals** — prefer explicit parameters, resolver objects, or frozen context.
6. **Architecture tests** — extend phase-specific guards.
7. **Combined focused validation** — build one deduplicated cluster plan with
   `python3 scripts/test_plan.py --explain` and run via `select-and-run-tests` once.
   Do not rerun overlapping clusters sequentially.
8. **ADR** — add or update `docs/decisions/` when a decision is accepted.
9. **Full CI once** — `scripts/ci.sh` on final stable tree only.
10. **Package smoke** — covered by final CI when package boundaries change.

## Stop conditions

- Stop when phase completion criteria are met and final CI is green
- Stop and report if a change would break CLI JSON, exit codes, or Pull/Push semantics

## Related skills

- `select-and-run-tests` — staged validation during migration
- `mutation-safety-audit` — mandatory for mutation-path changes
- `spell-sync-ci` — final CI and diagnostic reruns

## Finalize workspace snapshot

Before the final user report on modifying tasks:

1. Remove stale non-canonical archives (script default cleanup).
2. Run skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`.
3. Canonical paths: `$HOME/code.zip` and `$HOME/code.zip.sha256` only.
4. Include **Workspace snapshot** in the report and end with `CODE_ARCHIVE` / `SHA256`.
