# Agent development contract

Single source of truth for how this repository is developed and validated. The repository
owner defines intent, scope approval, and release policy. The Cursor Agent performs
implementation, testing, log interpretation, documentation updates, and evidence-based
reporting.

## Responsibilities

| Role | Owns |
|------|------|
| Repository owner | Intent, scope approval, concise final review, release/push policy |
| Cursor Agent | Code changes, focused validation, full CI, log analysis, docs/contracts sync |

The owner is not expected to grep CI logs, run individual test modules manually, fix
formatting by hand, or diagnose failing checks without agent support.

## Standard workflow

1. Read `AGENTS.md` and applicable `.cursor/rules/**` / `.cursor/skills/**`.
2. Capture Git baseline (`git status --short`, branch, HEAD).
3. Identify affected architecture boundaries (CLI, application, core, TUI).
4. Read implementation code and existing tests for the changed scope.
5. Make the smallest coherent change.
6. Run focused tests for the changed scope.
7. Run architecture guards (`tests/test_application_requests.py`, docs contract).
8. Run full `scripts/ci.sh`.
9. On failure: read the full CI log at the printed `CI_LOG` path; identify the primary error.
10. Update every affected document, test, and contract in the same task.
11. Produce an evidence-based report with exit codes and artifact paths.

## Evidence levels

| Level | Meaning |
|-------|---------|
| declared | Documented only |
| implemented | Code present |
| unit-tested | pytest covers module behavior |
| integration-tested | Cross-module or CLI scenario tests |
| CLI-contract-tested | JSON/exit-code contract tests |
| packaged | wheel/sdist build + twine check |
| runtime-accepted | Installed wheel smoke or manual platform validation |
| released | Owner-approved tag/publish (agent does not release by default) |

Unit tests do not prove runtime behavior on every host. Distinguish evidence level in reports.

## Failure handling

On CI or test failure the agent must:

- Read the full log at the path printed by `scripts/ci.sh` (`CI_LOG=...`).
- Read the machine-readable summary at `CI_SUMMARY=...`.
- Find the primary failing check or test using stable check/test IDs.
- Report stable check/test ID, component, expected, actual, relevant path, remediation.
- Re-run focused tests after fixes before full CI.

Do not ask the owner to diagnose failures or read raw logs.

## CI artifacts

- Entry point: `scripts/ci.sh` (non-interactive).
- Machine-readable summary: `.artifacts/ci/ci-summary.json` (schema version 1).
- Full log: `.artifacts/ci/ci.log` (rotated; retention keeps five completed runs).
- Final stdout block prints `CI_RESULT`, `CI_EXIT`, optional `CI_FAILED_ID`, `CI_SUMMARY`, `CI_LOG`.

## Prohibited repository content

Do not record external prompt authors, chat transcripts, model names, or maintainer-private
paths in committed files. Document only the supported Cursor Agent workflow and public
processes.

## Phase boundaries

Current package version comes from `pyproject.toml`. Phase 2B (typed application boundary)
is complete. Phase 2C (deterministic agent workflow and machine-readable CI) completes with
the automation commit. Phase 3 (explicit runtime / ContextVar removal) is **not** started.
