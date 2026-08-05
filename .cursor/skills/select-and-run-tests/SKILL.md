---
name: select-and-run-tests
description: Select the smallest local minimal validation set for current changes, execute without coverage, and defer full CI to publish.
---

# Select and run tests

Shared contract: `.cursor/README.md` § Shared contract.

## When to use

- After implementation chunks during modifying tasks
- Before declaring local minimal validation complete
- When choosing pytest targets for a changed scope

## Do not use

- As a substitute for full publish CI (`spell-sync-ci` with `--purpose publish`)
- With `--force` in normal agent workflows
- To skip safety clusters after mutation-path changes (commit gate adds them)

## Loop (edit)

```bash
python3 scripts/check_ci_necessity.py --purpose local --explain
python3 scripts/test_plan.py --dev-scope --explain
python3 scripts/run_dev_loop.py
```

L0 fills optional module tests toward the ~60s sample budget (`DEV_LOOP_SAMPLE_*`).
Use `--plan` to print the JSON plan without running. Use `--no-sample` only when
diagnosing a narrow failure. Skip when necessity is `no-action`. Prefer exact
failing nodes when reproducing a defect.

## Checkpoint

```bash
python3 scripts/run_dev_loop.py --commit-gate
```

Adds safety cluster tests when mutation paths change. Wall budget **120s**.
Commit gate does not sample-fill.

When application boundaries change:

```bash
python3 scripts/check_architecture.py --check
```

## Full gate (owner push / publish / final only)

Does **not** run full CI. Owner publish uses skill `preflight-publish` or
`spell-sync-ci`.

## Related

Report mode, selected clusters, `DEV_LOOP_*` / `DEV_LOOP_SAMPLE_*` lines, and that
full CI was deferred unless the owner requested publish.
