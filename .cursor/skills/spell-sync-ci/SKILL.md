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
python3 -m pytest tests/tui/test_<area>.py -q
python3 -m pytest tests/test_<area>.py -q
```

3. Run static checks:

```bash
python3 -m ruff check spell_sync tests scripts
python3 -m ruff format --check spell_sync tests scripts
python3 -m mypy spell_sync
python3 scripts/check-agent-config.py
python3 scripts/check-docs-contract.py
```

4. Run full CI:

```bash
scripts/ci.sh
```

Read `CI_LOG` and `CI_SUMMARY` from the printed paths. On failure, use `CI_FAILED_ID` as the
primary gate identifier. Summary schema version 2 includes `runId`, `historyLogPath`,
`historySummaryPath`, and `failedCheckId`. Installed-wheel smoke runs outside the checkout.
Do not ask the owner to diagnose failures.

Phase implementation uses `execute-current-phase`, `apply-phase-fixes`, and
`advance-current-phase` — not this skill alone.

## What ci.sh enforces

Via `scripts/ci_runner.py`:

| Check ID | Gate |
|----------|------|
| `bootstrap.python` | Python 3.11+ |
| `deps.install` / `deps.editable` | Tooling + editable install |
| `docs.style` | Markdown style |
| `docs.contract` | Documentation contracts |
| `agent.config` | Cursor agent configuration |
| `targets.capabilities` | Target registry |
| `ruff.check` / `ruff.format` | Lint and format (`spell_sync`, `tests`, `scripts`) |
| `mypy` | Types on `spell_sync/` |
| `tests.pytest` | Full pytest suite |
| `coverage.policy` | 100% lines, ≥96% branches on `spell_sync/` |
| `packaging.build` | wheel + sdist build |
| `packaging.twine` | Artifact validation |
| `packaging.wheel-smoke` | Installed wheel outside checkout (install, metadata, origin, CLI) |
| `smoke.init` / `smoke.lint` | Temporary project smoke |
| `smoke.tui` | Headless CLI scenarios |

## Common fixes

| Failure | Action |
|---------|--------|
| Coverage gap | Add behavior tests in existing modules; no `# pragma: no cover` unless unreachable |
| mypy | Fix types in `spell_sync/` |
| Docs style | Remove `---` horizontal rules; ensure Python 3.11+ in DEVELOPMENT/CONTRIBUTING |
| Agent config | Fix `.cursor/` frontmatter or stale facts flagged by `check-agent-config.py` |
| Docs contract | Fix stale API names or phase claims flagged by `check-docs-contract.py` |

## Stop conditions

- Stop when `scripts/ci.sh` exits **0**
- Stop and report if a failure requires an architectural decision or owner input
- Do not mask failures or weaken coverage gates

## Final report

- Focused commands run and results
- Static check results
- `scripts/ci.sh` exit code
- `CI_SUMMARY` and `CI_LOG` paths
- `CI_FAILED_ID` when CI failed
- Remaining failures with stable test/check ID if any
