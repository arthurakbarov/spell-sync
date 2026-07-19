---
name: spell-sync-ci
description: >-
  Run and fix spell-sync CI for a changed scope. Use when implementing features,
  fixing test failures, or verifying work before commit. Starts with focused
  tests, then ruff, mypy, and scripts/ci.sh.
---

# spell-sync CI

## When to use

- After code or test changes in the public repository
- Before declaring a task complete
- When CI or coverage failures need diagnosis and fix

## Do not use

- As a substitute for reading failing test output and fixing root causes
- To add meaningless tests solely to hit coverage lines
- To skip focused tests and run only full CI on every tiny edit

## Workflow

1. Identify changed scope (modules, screens, application layer).
2. Run focused tests first:

```bash
python3.11 -m pytest tests/tui/test_<area>.py -q
python3.11 -m pytest tests/test_<area>.py -q
```

3. Run static checks:

```bash
python3.11 -m ruff check spell_sync tests
python3.11 -m ruff format --check spell_sync tests
python3.11 -m mypy spell_sync
python3.11 scripts/check-agent-config.py
```

4. Run full CI:

```bash
scripts/ci.sh
```

## What ci.sh enforces

- `scripts/check-docs-style.sh` — no horizontal rules; Python 3.11+ in docs
- ruff check + format on `spell_sync` and `tests`
- mypy on `spell_sync`
- pytest with **100% line** and **≥96% branch** coverage on `spell_sync/`
- wheel build + `twine check`
- wheel install smoke (`version`, `--help`)
- `spell-sync lint --strict` smoke
- `tests/test_gui_smoke.py`

## Common fixes

| Failure | Action |
|---------|--------|
| Coverage gap | Add behavior tests in existing modules; no `# pragma: no cover` unless unreachable |
| mypy | Fix types in `spell_sync/` |
| Docs style | Remove `---` horizontal rules; ensure Python 3.11+ in DEVELOPMENT/CONTRIBUTING |
| Agent config | Fix `.cursor/` frontmatter or stale facts flagged by `check-agent-config.py` |

## Stop conditions

- Stop when `scripts/ci.sh` exits **0**
- Stop and report if a failure requires an architectural decision or owner input
- Do not mask failures or weaken coverage gates

## Final report

- Focused tests run and results
- Static check results
- `scripts/ci.sh` exit code
- Remaining failures with file/line if any
