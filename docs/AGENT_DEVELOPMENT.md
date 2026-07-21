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
7. Run focused tests via `select-and-run-tests` / `scripts/run_focused_tests.py`.
8. Run architecture guards when application boundaries change.
9. Run pre-final checks (`scripts/run_pre_final_checks.py`) before commits.
10. Set phase status to `awaiting-approval` when implementation is complete; commit all tracked changes locally.
11. Verify clean working trees (`git status --short`) in every affected repository.
12. Final task state: `git stash list` must be empty in the public spell-sync repository.
    Do not hide unfinished work in persistent Git stash between phases; preserve separate WIP
    on a named local branch with a normal commit instead.
13. Assess final validation need on the committed HEAD: `python3 scripts/check-ci-necessity.py --explain`.
14. Run full `scripts/ci.sh` **once** when necessity is `full-required` (final evidence on committed HEAD).
15. When necessity is `lightweight-sufficient`, run `python3 scripts/run_lightweight_validation.py` on committed HEAD.
16. Verify final evidence: `python3 scripts/check-ci-evidence.py` (`CI_EVIDENCE_RESULT=success`).
17. On failure: read `CI_LOG` and `CI_SUMMARY`; fix; focused rerun of failed gate; new corrective commit; clean tree; reassess necessity.
18. Update every affected document, test, and contract in the same task (before step 10).
19. On modifying tasks: workspace snapshot **after** successful evidence verification (see **Workspace snapshot**).
20. Re-verify `git status --short` and `python3 scripts/check-ci-evidence.py` after snapshot.
21. Produce an evidence-based report (see **Final report contract** below).

After successful final CI and evidence verification, do not modify tracked repository files
(ignored CI artifacts, owner snapshot outside repositories, and read-only inspection only).

Staged validation levels and deduplication rules: `docs/TESTING_STRATEGY.md`.

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
- Necessity planner: `python3 scripts/check-ci-necessity.py`.
- Lightweight validation: `python3 scripts/run_lightweight_validation.py`.
- Evidence verifier: `python3 scripts/check-ci-evidence.py` (`--release` requires exact HEAD).
- Machine-readable summary: `.artifacts/ci/ci-summary.json` (schema version 4).
- Lightweight receipt: `.artifacts/lightweight-validation/current.json`.
- Full log: `.artifacts/ci/ci.log` (rotated; retention keeps five completed run pairs).
- Final stdout block prints `CI_RESULT`, `CI_EXIT`, optional `CI_FAILED_ID`, `CI_SUMMARY`, `CI_LOG`.

Schema version 4 adds `gitHeadAtRun`, `repositoryTreeDigest`, `ciInputDigest`, `ciInputDigestBefore`,
`ciInputDigestAfter`, `ciInputStable`, `ciImpactSchemaVersion`, `evidenceScope`,
`reusableAcrossNonCiCommits`, and `changeClassesAtRun` alongside schema v3 fields (`schemaVersion`,
`runId`, `mode`, `finalEvidence`, `treeDigest`, `treeDigestBefore`, `treeDigestAfter`, `treeStable`,
`gitHead`, `gitBranch`, `gitDetached`, `historyAtCompletion`, `historyLogPath`, `historySummaryPath`,
`failedCheckId`, `checks`, `logPath`).

Full CI evidence is bound to CI-relevant inputs (`ciInputDigest`), not merely to the Git commit
identifier. A later non-CI commit may reuse successful full CI evidence only when the CI input digest
is unchanged and current lightweight validation succeeds (`CI_EVIDENCE_MATCH=reused-non-ci-change`).
Exact Git HEAD matching remains required for release, publication, and signed artifact workflows
(`CI_EVIDENCE_MATCH=exact-head` with `python3 scripts/check-ci-evidence.py --release`).

Only `mode=full` with `finalEvidence=true`, matching `ciInputDigest`, and
`CI_EVIDENCE_RESULT=success` from `scripts/check-ci-evidence.py` counts as final CI evidence.
Diagnostic runs (`--only`, `--from`, `--resume-failed`) do not.

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

## Test selection
- changed scope, clusters, skipped duplicate commands, reused run keys
- full CI runs attempted (expected: 1) and reason for any additional run

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

When the task changed workspace state in any repository, section **14. Workspace snapshot** (see
**Workspace snapshot** below) must include:

```markdown
## 14. Workspace snapshot

- result: success
- created: true
- verified: true
- path: `$HOME/code.zip` (only file persisted on disk)
- SHA-256: `...` (from `SNAPSHOT_SHA256`; response only)
- size: `... bytes`
- archive file count: `...`
- stale archives removed: `...`
- repositories included:
  - spell-sync
  - spell-sync-dev
  - spell-words
- previous canonical archive replaced: yes
```

When the task was read-only:

```markdown
## 14. Workspace snapshot

- result: skipped
- created: false
- reason: read-only task
- existing path: `$HOME/code.zip`
```

## Workspace snapshot

Every **modifying task** — workspace state changed in spell-sync, spell-sync-dev, or spell-words —
must finalize the owner workspace snapshot **before** the final user report.

| Persist on disk | Response only (never write to disk) |
|-----------------|-------------------------------------|
| `$HOME/code.zip` | SHA256 in report §14, report footer, and `SNAPSHOT_SHA256` stdout |

Procedure — skill `create-code-snapshot` in spell-sync-dev:

1. After commits, clean trees, final full CI, and `python3 scripts/check-ci-evidence.py` success: `--force`, then `--check`.
2. Re-run `git status --short` and `python3 scripts/check-ci-evidence.py`; both must stay green.
3. Canonical path: `$HOME/code.zip` only. No timestamped alternates; no hash sidecar file
   (`code.zip.sha256`) on disk.
4. Read-only tasks: skip recreation; report §14 with `result: skipped`.

Report footer:

```text
CODE_ARCHIVE
<absolute path to $HOME/code.zip>

SHA256
<digest from SNAPSHOT_SHA256>
```

Maintainer script details: private `docs/OWNER_WORKSPACE_SNAPSHOT.md` in spell-sync-dev (not
shipped in the public package).

Do not include huge raw logs. Include failed check ID and a short relevant excerpt only when unresolved.
