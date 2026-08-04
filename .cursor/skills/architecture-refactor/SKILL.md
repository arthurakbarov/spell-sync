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

1. **Dependency audit** — map imports before and after; no reverse dependencies.
2. **Safety contracts** — list Pull/Push/Recovery/lock/journal invariants at risk (`mutation-safety-audit` when mutation paths change).
3. **Migration without parallel paths** — remove or migrate callers; no permanent compatibility wrappers.
4. **Architecture guard updates** — extend `scripts/check_architecture.py` and `tests/test_check_architecture.py` when exports or boundaries change.
5. **Focused tests** — L0/L1 via `python3 scripts/run_dev_loop.py` and `select-and-run-tests`.
6. **Docs and ADR** — update `docs/architecture/`, `docs/PROJECT_MAP.md`, and `docs/decisions/` when decisions change.
7. **Commits and clean tree** — local commits; L1 `run_dev_loop.py --commit-gate`; `git status --short` clean.
8. **Local necessity** — `python3 scripts/check_ci_necessity.py --purpose local --explain` (no full CI when `commit-gate-sufficient`).
9. **L2 publish only** — `scripts/ci.sh` on committed HEAD when `--purpose publish` / owner final; then `check_ci_evidence.py`.
10. **Installed-wheel smoke** — when package boundaries change (included in L2).

## Stop conditions

- Stop when phase completion criteria are met and L1 is green (L2 only if publish requested)
- Stop and report if a change would break CLI JSON, exit codes, or Pull/Push semantics

## Related skills

- `select-and-run-tests` — staged L0/L1 validation during migration
- `mutation-safety-audit` — mandatory for mutation-path changes
- `diagnostics-change` — structured event pipeline changes
- `spell-sync-ci` — L2 publish CI and diagnostic reruns

## Finalize workspace snapshot

Modifying tasks — after L1 (`run_dev_loop.py --commit-gate`). When L2 ran, require
`python3 scripts/check_ci_evidence.py` success first.
Skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
