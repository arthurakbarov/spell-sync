# Agent development contract

Single source of truth for how this repository is developed and validated. The repository
owner defines intent, scope approval, and release policy. The Cursor Agent performs
implementation, testing, log interpretation, documentation updates, and evidence-based
reporting.

## Responsibilities

| Role | Owns |
|------|------|
| Repository owner | Intent, scope approval, phase acceptance, release/push policy |
| Cursor Agent | Code changes, focused validation, full CI, log analysis, docs/contracts sync |
| Repository automation | Static checks, tests, coverage, packaging, machine-readable CI summary |

The owner is not expected to grep CI logs, run individual test modules manually, fix
formatting by hand, or diagnose failing checks without agent support.

## Short commands

After bootstrap, later sessions can use:

```text
Выполни skill execute-current-phase.
```

```text
Исправь перечисленные дефекты через skill apply-phase-fixes: ...
```

```text
Текущая фase принята. Выполни skill advance-current-phase, затем execute-current-phase.
```

Skills live under `.cursor/skills/`. Canonical process detail is in this document.

## Standard workflow

1. Read `AGENTS.md` and applicable `.cursor/rules/**` / `.cursor/skills/**`.
2. Read the architecture status block in `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md`.
3. Capture Git baseline for all three workspace repositories (`HEAD`, branch, `git status --porcelain=v2 --untracked-files=all`).
4. Identify affected architecture boundaries (CLI, application, core, TUI).
5. Read implementation code and existing tests for the changed scope.
6. Make the smallest coherent change for the **current phase only**.
7. Run focused tests for the changed scope.
8. Run architecture guards (`tests/test_application_requests.py`, phase-specific tests).
9. Run full `scripts/ci.sh`.
10. On failure: read `CI_LOG` and `CI_SUMMARY`; identify the primary error via stable IDs.
11. Update every affected document, test, and contract in the same task.
12. Produce an evidence-based report (see **Final report contract** below).

## Current-phase lifecycle

Statuses in the architecture status block:

| Status | Meaning |
|--------|---------|
| `not-started` | Planned; no implementation yet |
| `in-progress` | Agent is implementing (must be `current`) |
| `awaiting-approval` | Implementation complete; owner review (must be `current`) |
| `blocked` | Cannot proceed until blocker removed |
| `complete` | Owner accepted via `advance-current-phase` |

Rules:

- Exactly one `current` phase id
- `current` must not point to `complete`
- At most one `in-progress` and one `awaiting-approval`
- `in-progress` and `awaiting-approval` must be the `current` phase
- Implementation sets `awaiting-approval`; only `advance-current-phase` sets `complete`
- Next phase stays `not-started` until owner approval and advance

## Phase approval and corrective cycle

1. Agent finishes phase → status `awaiting-approval` → final report → stop.
2. Owner accepts → `advance-current-phase` → current phase `complete`, next phase `current` + `not-started`.
3. Owner lists defects → `apply-phase-fixes` → stay `awaiting-approval` → stop.

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
- Machine-readable summary: `.artifacts/ci/ci-summary.json` (schema version 2).
- Full log: `.artifacts/ci/ci.log` (rotated; retention keeps five completed run pairs).
- Final stdout block prints `CI_RESULT`, `CI_EXIT`, optional `CI_FAILED_ID`, `CI_SUMMARY`, `CI_LOG`.

Schema v2 fields include `schemaVersion`, `runId`, `historyLogPath`, `historySummaryPath`, and
`failedCheckId` when a check fails.

Installed-wheel smoke runs outside the repository checkout so the local tree cannot shadow the
installed package.

## Prohibited repository content

Do not record external prompt authors, chat transcripts, model names, maintainer-private
paths, archive handoff workflows, review ZIPs, or upload instructions in committed files.
Document only the supported Cursor Agent workflow and public processes.

## Phase boundaries

Current package version comes from `pyproject.toml`. Completed automation phases (2C–2E) established
deterministic CI and agent workflow. Phase 3 (explicit runtime) is tracked in the architecture
implementation document.

## Final report contract

Every completed phase or corrective task returns:

```markdown
# Final report

## 1. Baseline
- starting HEAD, package version, clean status, baseline validators, baseline CI

## 2. Current phase
- phase ID, starting status, goal, scope

## 3. Inventory
- affected modules, dependency paths, contracts, risks

## 4. Implementation
- files changed, APIs changed, architecture decisions, removed legacy paths

## 5. Tests added or changed
- test files, regression cases, architecture guards

## 6. Focused validation
| Command | Result |

## 7. Full CI
- CI_RESULT, CI_EXIT, CI_FAILED_ID, CI_SUMMARY, CI_LOG

## 8. Packaging
- wheel/sdist, installed-wheel smoke, package version, import origin when applicable

## 9. Documentation
- tracker, ADR, rules/skills, public docs

## 10. Git
- commits, diff stat, final status, remotes unchanged

## 11. Current architecture status
- current phase, final status, next phase not started

## 12. Known limitations
- factual remaining limitations only

## 13. Scope confirmations
- next phase not started; no push/tag/release; no unrelated product changes
```

When the task changed workspace state in any repository, section **14. Workspace snapshot** must include:

```markdown
## 14. Workspace snapshot

- result: success
- created: true
- path: `<home>/code.zip`
- SHA-256: `...`
- size: `... bytes`
- archive file count: `...`
- repositories included:
  - spell-sync
  - spell-sync-dev
  - spell-words
- previous archive replaced: yes
```

When workspace state did not change:

```markdown
## 14. Workspace snapshot

- result: skipped
- created: false
- reason: workspace unchanged
- existing path: `<home>/code.zip`
```

Modifying tasks must finalize the owner-controlled workspace snapshot via the private maintainer
skill `create-code-snapshot` before the final report. Full owner-controlled workspace snapshot for
offline inspection and preservation of the exact completed task state.

Modifying-task reports end with:

```text
CODE_ARCHIVE
<absolute path to $HOME/code.zip>

SHA256
<digest>
```

Do not include huge raw logs. Include failed check ID and a short relevant excerpt only when unresolved.
