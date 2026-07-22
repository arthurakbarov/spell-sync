---
name: run-time-controlled-command
description: >-
  Run a registered development or CI command under execution budget control with
  admission, immutable plan, and bounded subprocess termination.
---

# Run time-controlled command

## When to use

- Running an expensive command outside integrated runners
- Invoking a one-off bounded pytest or validator with explicit execution ID
- Investigating timeout behavior with known budget metadata

## Do not use

- For product Pull, Push, Recovery, or mutation CLI paths
- With `tail`, `tee`, or pipeline wrappers around CI
- To bypass CI necessity or functional evidence checks
- With `--force` to ignore duplicate-active protection without cause

## Workflow

1. **Assess necessity** — when the command is part of final validation:

```bash
python3 scripts/check-ci-necessity.py --explain
```

Skip execution when result is `no-action` and the command is not required.

2. **Choose execution ID** — use stable IDs from `tests/execution-budget.toml` and
   `scripts/execution_control/mappings.py`:

| Context | Example ID |
|---------|------------|
| Focused module gate | `gate:focused-module` |
| Focused cluster gate | `gate:focused-cluster` |
| Pre-final gate | `gate:pre-final` |
| Full CI gate | `gate:full-ci` |
| CI check child | `ci:pytest`, `ci:mypy`, … |
| Unknown fallback | `gate:unknown` |

Prefer integrated runners when available:

```bash
python3 scripts/run_focused_tests.py
python3 scripts/run_pre_final_checks.py
scripts/ci.sh
```

3. **Run through controller** — direct invocation:

```bash
python3 scripts/run_with_budget.py \
  --execution-id <id> \
  [--mode module|cluster|full-ci] \
  [--required] \
  [--test-files N] \
  [--test-nodes N] \
  [--coverage] [--tui] [--packaging] \
  -- <command...>
```

4. **Read plan output** — before execution starts, confirm:

```text
EXECUTION_ID=...
EXECUTION_EXPECTED_SECONDS=...
EXECUTION_SOFT_SECONDS=...
EXECUTION_HARD_SECONDS=...
EXECUTION_ADMISSION_DECISION=run|reuse|...
```

When `EXECUTION_ADMISSION_DECISION=reuse` or `EXECUTION_RESULT=reused`, do not treat the
run as new functional evidence.

5. **Read result** — after completion:

```text
EXECUTION_RESULT=success|success-slow|failed|timeout-hard|...
EXECUTION_DURATION_SECONDS=...
EXECUTION_LEARNING_ACCEPTED=true|false
```

6. **Handle timeout** — on `timeout-hard` or `timeout-stall`:

- Read `CI_TIMEOUT_CHECK_ID` or `EXECUTION_ACTIVE_CHILD` when present
- Inspect bundle under `$XDG_STATE_HOME/spell-sync/execution-control/timeouts/<run-id>/`
- Run at most one narrow diagnostic retry (`diagnosticRetries ≤ 1`)
- Do not automatically retry the broad parent gate

7. **Handle duplicate block** — when `EXECUTION_RESULT=blocked` and
   `EXECUTION_FAILED_ID=execution.duplicate-active`, wait for the owner or investigate the
   active PID; do not start a parallel duplicate.

8. **Report** — include execution ID, admission decision, durations, reuse skips, and
   duplicate blocks in the task report.

## Stop conditions

- Stop when `EXECUTION_RESULT` is terminal and exit code matches expectation
- Stop and report on `blocked-duplicate` without forcing parallel execution
- Stop after one diagnostic retry on timeout; fix root cause before the next final gate

## See also

- Rule: `.cursor/rules/execution-time-control.mdc`
- Doc: `docs/EXECUTION_TIME_CONTROL.md`
- CI skill: `spell-sync-ci`
- Test selection: `select-and-run-tests`
