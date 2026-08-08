# Agent development contract

Single source of truth for how this repository is developed and validated. The repository
owner defines intent, scope approval, and release policy. The Cursor Agent performs
implementation, testing, log interpretation, documentation updates, and evidence-based
reporting.

## Responsibilities

| Role | Owns |
|------|------|
| Repository owner | Intent, scope approval, phase acceptance, release/push policy |
| Cursor Agent | Code changes, **local commits anytime on any branch** (see `docs/GIT-WORKFLOW.md`), local minimal validation, full CI only before push/release, docs/contracts sync |
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
Текущая фаза принята. Выполни skill advance-current-phase, затем execute-current-phase.
```

Skills live under `.cursor/skills/`. Canonical process detail is in this document.

## Standard workflow

1. Read `AGENTS.md` and applicable `.cursor/rules/**` / `.cursor/skills/**`.
2. Read the architecture status block in `docs/ARCHITECTURE_V1_IMPLEMENTATION.md`.
3. Capture Git baseline for all three workspace repositories (`HEAD`, branch, `git status --porcelain=v2 --untracked-files=all`).
4. Inspect rollup: `python3 scripts/agent_context.py` (optional `--json`) for product
   branch/dirty/necessity/suggested runners and sibling workspace repos when present
   (`spell-words`, `spell-sync-dev` via env or conventional layout).
5. Identify affected architecture boundaries (CLI, application, core, TUI).
6. Read implementation code and existing tests for the changed scope.
7. Make the smallest coherent change for the **current phase only**.
8. Run **edit loop** validation: `python3 scripts/run_dev_loop.py` (no coverage).
9. Run architecture guards when application boundaries change.
10. Update every affected document, test, and contract in the same task.
11. Run **commit gate** while the tree still shows the change (or with an explicit
    `--base` / `--files` scope): `python3 scripts/run_dev_loop.py --commit-gate` (≤120s).
    Do not commit first and then rely on a clean-tree gate — `run_dev_loop` defaults to
    working-tree vs HEAD, so a clean tree validates nothing.
12. Set phase status to `awaiting-approval` when implementation is complete; **then** commit
    all tracked changes locally (local commits do not require owner approval).
13. Verify clean working trees (`git status --short`) in every affected repository.
14. Final task state: `git stash list` must be empty in the public spell-sync repository.
    Do not hide unfinished work in persistent Git stash between phases; preserve separate WIP
    on a named local branch with a normal commit instead.
15. Assess local necessity: `python3 scripts/check_ci_necessity.py --purpose local --explain`.
16. When result is `commit-gate-sufficient` or `lightweight-sufficient` / `no-action`: **do not**
    run full CI. Use lightweight validation only when `lightweight-sufficient`.
17. Run **full CI** (`scripts/ci.sh`) only for `--purpose publish` (`full-required`), explicit
    owner “final/push/release”, or `release-candidate` workflows.
18. Verify `python3 scripts/check_ci_evidence.py` **only** after full CI (or when reusing valid
    publish evidence). Ordinary polish tasks may finish without new full-CI evidence.
19. On full CI failure: read `CI_LOG` / `CI_SUMMARY`; fix; focused failed-gate rerun; new commit;
    clean tree; reassess with `--purpose publish`.
20. On modifying tasks: workspace snapshot after commit gate success (and full CI evidence when full CI ran).
21. Produce an evidence-based report (see **Final report contract** below).

Staged validation modes: `docs/TESTING_STRATEGY.md` (local minimal + full CI).

Execution time control (admission, immutable timing plans, bounded subprocess runs) applies to
full CI and registered expensive commands: `docs/EXECUTION_TIME_CONTROL.md`. Local minimal
`run_dev_loop.py` is outside edit-loop admission so micro validation is not blocked. Rule:
`.cursor/rules/execution-time-control.mdc`. Skill: `run-time-controlled-command`.

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
- Necessity planner: `python3 scripts/check_ci_necessity.py`.
- Lightweight validation: `python3 scripts/run_lightweight_validation.py`.
- Evidence verifier: `python3 scripts/check_ci_evidence.py` (`--release` requires exact HEAD).
- Machine-readable summary: `.artifacts/ci/ci-summary.json` (schema version 5).
- Lightweight receipt: `.artifacts/lightweight-validation/current.json`.
- Full log: `.artifacts/ci/ci.log` (rotated; retention keeps five completed run pairs).
- Final stdout block prints `CI_RESULT`, `CI_EXIT`, optional `CI_FAILED_ID`, `CI_SUMMARY`, `CI_LOG`.

Schema version 5 adds environment identity fields: `environmentFingerprint`,
`environmentFingerprintBefore`, `environmentFingerprintAfter`, `environmentStable`,
`environmentContractDigest`, `pyprojectDigest`, `uvLockDigest`, `installedEnvironmentDigest`,
`pythonImplementation`, `pythonVersion`, `pythonCacheTag`, `uvVersion`, and
`selectedDependencyGroups`. Full CI must keep environment identity stable for the run; drift fails
with `CI_FAILED_ID=ci.environment-changed`.

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
(`CI_EVIDENCE_MATCH=exact-head` with `python3 scripts/check_ci_evidence.py --release`).

Only `mode=full` with `finalEvidence=true`, matching `ciInputDigest`, and
`CI_EVIDENCE_RESULT=success` from `scripts/check_ci_evidence.py` counts as final CI evidence.
Diagnostic runs (`--only`, `--from`, `--resume-failed`) do not.

Installed-wheel smoke runs outside the repository checkout so the local tree cannot shadow the
installed package.

## Prohibited repository content

Do not record external prompt authors, chat transcripts, model names, maintainer-private
paths, archive handoff workflows, review ZIPs, or upload instructions in committed files.
Document only the supported Cursor Agent workflow and public processes.

## Phase boundaries

Current package version comes from `pyproject.toml`. Architecture migration phases 1–10 are
**complete** (see `docs/ARCHITECTURE_V1_IMPLEMENTATION.md`). The tracker current focus is
`owner-publish` (release, manual validation, and related owner-initiated work — not a new
architecture migration). Post-v1 engineering ops are complete.

## Final report contract

Every completed phase or corrective task returns:

```markdown
# Final report

## 1. Baseline
- starting HEAD, package version, clean status, baseline validators, baseline CI
- highest evidence level already held (from `docs/CONTRACTS.md` § Evidence levels)

## 2. Current phase
- phase ID, starting status, goal, scope

## 3. Inventory
- affected modules, dependency paths, contracts, risks
- residual IDs in play (from PRODUCT_COMPLETION / ROADMAP) when relevant

## 4. Implementation
- files changed, APIs changed, architecture decisions, removed legacy paths

## 5. Tests added or changed
- test files, regression cases, architecture guards

## 6. Focused validation
| Command | Result |

## Test selection
- changed scope, clusters, skipped duplicate commands, reused run keys
- Local minimal budget: wall vs 60s/120s (`DEV_LOOP_BUDGET_STATUS`); full CI: expected/soft vs actual
- full CI runs attempted (expected: 0 for polish, 1 before push/release) and reason for any additional run
- evidence level reached by this validation (must not exceed what commands support)

## 7. Full CI
- CI_RESULT, CI_EXIT, CI_FAILED_ID, CI_SUMMARY, CI_LOG
- triage: `python3 scripts/dev_runs.py index` / `show <run-id>` when useful

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
- residuals still open (prefer stable IDs from PRODUCT_COMPLETION.md / ROADMAP.md)
- no false equivalences from docs/CONTRACTS.md claimed as proven
- validation was not re-run when the When-not-to-rerun table in docs/WORKFLOW.md forbade it
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

1. After commits and clean trees: run commit gate (`run_dev_loop.py --commit-gate`) and
   `python3 scripts/check_ci_necessity.py --purpose local --explain`. Ordinary polish tasks
   may snapshot without a new full CI. When the owner requested push/release (full CI), require
   successful `scripts/ci.sh` evidence and `python3 scripts/check_ci_evidence.py` first.
2. Create snapshot with `--force`, then `--check`.
3. Re-run `git status --short` (must stay clean). Re-run `check_ci_evidence.py` only when
   full CI was part of this task.
4. Canonical path: **`$HOME/code.zip` only** — the archive must live in the owner home
   directory (`Path.home() / "code.zip"`), not under the workspace tree. Do **not** use paths
   such as `$SPELL_SYNC_WORKSPACE/code.zip`, `~/code/code.zip`, or any repository parent
   directory. Prefer explicit `--output "$HOME/code.zip"` or omit `--output` (script default).
   No timestamped alternates; no hash sidecar file (`code.zip.sha256`) on disk.
5. Read-only tasks: skip recreation; report §14 with `result: skipped`.

Report footer:

```text
CODE_ARCHIVE
$HOME/code.zip

SHA256
<digest from SNAPSHOT_SHA256>
```

The report must give the resolved absolute home path (for example `/Users/<owner>/code.zip`), not
a workspace-relative path.

Maintainer script details: private `docs/OWNER_WORKSPACE_SNAPSHOT.md` in spell-sync-dev (not
shipped in the public package).

Do not include huge raw logs. Include failed check ID and a short relevant excerpt only when unresolved.
