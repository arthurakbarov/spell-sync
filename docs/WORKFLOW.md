# Development workflow

Operator lifecycle for spell-sync. Git: [GIT-WORKFLOW.md](GIT-WORKFLOW.md).
Done: [ENGINEERING_COMPLETION.md](ENGINEERING_COMPLETION.md) +
[PRODUCT_COMPLETION.md](PRODUCT_COMPLETION.md). Artifacts:
[ARTIFACTS-AND-STATE.md](ARTIFACTS-AND-STATE.md). Agent detail:
[AGENT_DEVELOPMENT.md](AGENT_DEVELOPMENT.md).

## Before work

```bash
python3 scripts/agent_context.py
python3 scripts/project_environment.py check
python3 scripts/run_recovery_smoke.py   # or: ss recovery-smoke
```

Maintainer dispatcher (aliases `scripts/ss` / `scripts/dev`):

```bash
python3 scripts/ss.py --list
ss edit-loop
ss commit-gate
ss runs-index
```

## Edit loop (~60s sample)

```bash
python3 scripts/run_dev_loop.py
python3 scripts/run_dev_loop.py --plan          # plan only, no execution
python3 scripts/run_dev_loop.py --cluster pull  # logical checkpoint
```

L0 keeps must-keep affected tests (plus a small smoke core), then fills optional
module tests toward the ~60s budget (`DEV_LOOP_SAMPLE_*`). Disable fill with
`--no-sample`.

Do **not** run in the edit loop:

- `scripts/ci.sh`
- packaging / wheel-smoke
- coverage walls

## Checkpoint (commit boundary, ~120s)

```bash
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_ci_necessity.py --purpose local --explain
```

Commit gate adds safety cluster tests when mutation paths change. It does not
sample-fill.

## Full gate (owner push / publish / final only)

```bash
python3 scripts/preflight_publish.py
python3 scripts/preflight_publish.py --execute
```

Or `scripts/ci.sh` then `python3 scripts/check_ci_evidence.py`.

## Triage

```bash
python3 scripts/dev_runs.py index          # also appends CI rows to .artifacts/ci/runs-index.jsonl
python3 scripts/dev_runs.py index --no-persist
python3 scripts/dev_runs.py failures
python3 scripts/dev_runs.py show <run-id>
```

Do not pipe CI through `tail` / `tee`.

## When not to rerun

| Situation | Action |
|-----------|--------|
| Commit-gate already green on this HEAD, no new commits or CI-relevant dirty files | Do not re-run commit-gate or full CI |
| Necessity is `commit-gate-sufficient`, `lightweight-sufficient`, or `no-action` | Do not run `scripts/ci.sh` |
| Failure was a single focused pytest node; fix landed | Rerun that node, then once the affected module/cluster — not full CI |
| Runtime-only drift (real app open, host dictionary changed) while repo declaration correct | Rebuild product preview/doctor on the host; do not treat as a repo CI failure |
| Full CI green and only non-CI docs/agent-prose changed with unchanged `ciInputDigest` | Prefer lightweight / evidence reuse over another full `scripts/ci.sh` |
| Workspace snapshot already verified for this clean HEAD | Do not rebuild the snapshot archive unless the tree changed |

Identical successful commands on an unchanged tree must not be repeated. Prefer
`python3 scripts/check_session.py` within one agent arc when available.

## Agent report contract

Every completed modifying task returns the final report template in
[AGENT_DEVELOPMENT.md](AGENT_DEVELOPMENT.md) (Baseline through Scope confirmations,
plus Workspace snapshot §14 when the workspace changed).

Agents must not:

- claim a higher evidence level than Validation / Full CI sections support
- imply false equivalences from [CONTRACTS.md](CONTRACTS.md)
- start the next architecture phase without owner approval
- push, tag, release, or publish unless the owner asked in the same message

## Surfaces

| Role | Entry |
|------|-------|
| Inspect | `python3 scripts/agent_context.py` |
| Session reuse | `python3 scripts/check_session.py` |
| Commands | `config/dev-commands.json` + `config/dev-surface.json` |
| Honesty | [CONTRACTS.md](CONTRACTS.md), [FEATURE_MATRIX.md](FEATURE_MATRIX.md) |
| Open work | [ROADMAP.md](ROADMAP.md) |
