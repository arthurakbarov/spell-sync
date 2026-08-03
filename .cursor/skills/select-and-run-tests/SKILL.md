---
name: select-and-run-tests
description: Select the smallest sufficient non-duplicated validation set for the current changes, execute it, and record reusable evidence.
---

# Select and run tests

## When to use

- After implementation chunks during modifying tasks
- Before declaring focused validation complete
- When choosing pytest targets for a changed scope

## Do not use

- As a substitute for final full CI (`spell-sync-ci` skill)
- With `--force` in normal agent workflows
- To skip safety clusters after mutation-path changes

## Step 0 — admission

Assess CI necessity before expensive commands:

```bash
python3 scripts/check_ci_necessity.py --explain
```

When result is `no-action`, skip redundant validation. Integrated runners apply execution
admission and may print `EXECUTION_RESULT=reused` without subprocess start.

## Step 1 — classify change

Determine changed files, behavior, risk level, and relevant clusters:

```bash
python3 scripts/test_plan.py --explain
```

## Step 2 — Level 0 (defect reproduction)

When a specific failure exists, run the exact test until green. Do not run the full
cluster after every edit.

## Step 3 — Level 1 (module validation)

When implementation is stable for the touched module:

```bash
python3 scripts/run_focused_tests.py
```

## Step 4 — Level 2 (risk cluster)

When Level 1 is green, run the deduplicated cluster once if not already covered by Step 3.

## Step 5 — static focused validation

For changed Python files only:

```bash
python3 -m ruff check <changed-python-files>
python3 -m ruff format --check <changed-python-files>
```

Run mypy on changed production modules when types changed. Full mypy remains in final CI.

Do not run full-repository Ruff after every small edit.

## Step 6 — return evidence

Report:

- selected files and clusters
- commands and durations
- skipped duplicate commands (`TEST_RUN_REASON=already-passed-for-current-state`)
- execution reuse skips (`EXECUTION_RESULT=reused`)
- remaining final gates (full CI once)

This skill does not run full CI.
