---
name: run-time-controlled-command
description: >-
  Run a registered development or CI command under execution budget control with
  admission, immutable plan, and bounded subprocess termination.
---

# Run time-controlled command

Shared contract: `.cursor/README.md` § Shared contract.

## When to use

- Running an expensive command outside integrated runners
- Invoking a one-off bounded pytest or validator with explicit execution ID
- Investigating timeout behavior with known budget metadata

## Do not use

- For product Pull, Push, Recovery, or mutation CLI paths
- With `tail`, `tee`, or pipeline wrappers around CI
- To bypass CI necessity or functional evidence checks
- With `--force` to ignore duplicate-active protection without cause

## Loop (edit)

Prefer integrated runners:

```bash
python3 scripts/run_dev_loop.py
python3 scripts/run_focused_tests.py
```

Direct one-off:

```bash
python3 scripts/run_with_budget.py \
  --execution-id gate:focused-module \
  --mode module \
  -- <command...>
```

Stable IDs: `tests/execution-budget.toml`, `scripts/execution_control/mappings.py`
(`gate:focused-module`, `gate:focused-cluster`, `gate:pre-final`, `gate:full-ci`,
`ci:pytest`, …).

## Checkpoint

```bash
python3 scripts/check_ci_necessity.py --purpose local --explain
python3 scripts/run_dev_loop.py --commit-gate
```

Skip when necessity is `no-action`. Confirm plan lines before work starts:

```text
eta: expected ~…
EXECUTION_ID=...
EXECUTION_EXPECTED_SECONDS=...
EXECUTION_SOFT_SECONDS=...
EXECUTION_HARD_SECONDS=...
EXECUTION_ADMISSION_DECISION=run|reuse|...
```

Interactive prompts: `--prompts N` on `run_with_budget.py` (each +5s to ETA/wall only).

## Full gate (owner push / publish / final only)

```bash
python3 scripts/run_with_budget.py --execution-id gate:full-ci --mode full-ci --required -- scripts/ci.sh
# or: scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

## Related

On `timeout-hard` / `timeout-stall`: at most one diagnostic retry; inspect
`$XDG_STATE_HOME/spell-sync/execution-control/timeouts/<run-id>/`. Do not auto-retry
the broad parent gate.

On `execution.duplicate-active`: do not start a parallel duplicate.

Report `EXECUTION_*` lines, reuse skips, and duplicate blocks.

- Rule: `.cursor/rules/execution-time-control.mdc`
- Doc: `docs/EXECUTION_TIME_CONTROL.md`
- Skills: `spell-sync-ci`, `select-and-run-tests`
