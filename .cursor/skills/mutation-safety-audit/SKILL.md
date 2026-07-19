---
name: mutation-safety-audit
description: >-
  Audit Pull, Push, config writes, transaction, journal, Recovery, operation lock,
  setup, and target settings changes for safety invariants. Use before merging
  mutation-path changes. Does not auto-fix code.
---

# Mutation safety audit

## When to use

- Changes to Pull, Push, config writes, transaction engine, journal, Recovery, operation lock
- New or modified setup or target-settings execution paths
- TUI flows that trigger mutations

## Do not use

- For read-only UI or documentation-only changes
- To automatically rewrite code before identifying a concrete defect

## Pre-read

1. `@docs/ARCHITECTURE.md`
2. `@docs/RECOVERY.md`
3. Relevant modules:

```text agent-config-paths
spell_sync/push_prepared.py
spell_sync/push_transaction.py
spell_sync/push_journal.py
spell_sync/operation_lock.py
spell_sync/project_setup/target_settings.py
```

## Checklist

- [ ] Effective project resolved from wordlist path
- [ ] Strict config validation before mutation
- [ ] Pending Recovery blocks new writes
- [ ] Project operation lock acquired and released
- [ ] Exact immutable preview used for confirmation and execution
- [ ] Plan/update ID matches at execution time
- [ ] Config or target fingerprint checked before write
- [ ] External change / stale preview stops safely without overwrite
- [ ] Atomic writes for config and dictionaries
- [ ] Snapshots created before target writes (Push)
- [ ] Rollback on failure; incomplete rollback preserves Recovery artifacts
- [ ] Recovery does not overwrite external changes
- [ ] Idempotent recovery discard after success
- [ ] No user words in history or technical logs
- [ ] Target settings update does not touch dictionaries or wordlist

## Regression tests

Run relevant suites:

```bash
python3.11 -m pytest tests/test_pull_safety.py tests/test_transaction_safety.py -q
python3.11 -m pytest tests/test_tui_mutation_safety.py tests/test_tui_recovery_safety.py -q
python3.11 -m pytest tests/test_target_settings.py tests/test_project_setup.py -q
```

## Stop conditions

- All checklist items verified or explicitly N/A with justification
- Safety regression tests green
- Report any invariant gap before proceeding

## Final report

- Files changed in mutation path
- Checklist pass/fail per item
- Test results
- Identified gaps and recommended fixes (do not apply fixes unless asked)
