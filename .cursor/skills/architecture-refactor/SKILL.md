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
5. **Focused tests** — one deduplicated cluster plan via `python3 scripts/test_plan.py --explain` and `select-and-run-tests`.
6. **Docs and ADR** — update `docs/architecture/`, `docs/PROJECT_MAP.md`, and `docs/decisions/` when decisions change.
7. **Pre-final checks** — `python3 scripts/run_pre_final_checks.py` before commits.
8. **Commits and clean tree** — local commits; `git status --short` clean before final CI.
9. **Full CI once** — `scripts/ci.sh` on committed HEAD when `check-ci-necessity` requires it.
10. **Final evidence** — `python3 scripts/check_ci_evidence.py`.
11. **Installed-wheel smoke** — when package boundaries or entry points change (included in full CI).

## Stop conditions

- Stop when phase completion criteria are met and final CI evidence is green
- Stop and report if a change would break CLI JSON, exit codes, or Pull/Push semantics

## Related skills

- `select-and-run-tests` — staged validation during migration
- `mutation-safety-audit` — mandatory for mutation-path changes
- `diagnostics-change` — structured event pipeline changes
- `spell-sync-ci` — final CI and diagnostic reruns

## Finalize workspace snapshot

Modifying tasks only — before the final report: skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`; canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`. SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
