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
python3 scripts/dev_runs.py failures
python3 scripts/dev_runs.py show <run-id>
```

Do not pipe CI through `tail` / `tee`.

## Surfaces

| Role | Entry |
|------|-------|
| Inspect | `python3 scripts/agent_context.py` |
| Commands | `config/dev-commands.json` + `config/dev-surface.json` |
| Honesty | [CONTRACTS.md](CONTRACTS.md), [FEATURE_MATRIX.md](FEATURE_MATRIX.md) |
| Open work | [ROADMAP.md](ROADMAP.md) |
