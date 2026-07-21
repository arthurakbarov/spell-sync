---
name: spell-sync-ci
description: >-
  Run and fix spell-sync CI for a changed scope. Use when implementing features,
  fixing test failures, or verifying work before commit. Starts with
  select-and-run-tests, then one final full scripts/ci.sh on committed HEAD.
---

# spell-sync CI

## When to use

- Before declaring a modifying task complete (final full CI once on committed HEAD)
- When CI or coverage failures need diagnosis and fix
- To rerun a **single failed gate** during fix loops

## Do not use

- As a substitute for reading failing test output and fixing root causes
- To add meaningless tests solely to hit coverage lines
- To run full CI on every tiny edit
- To repeat full CI without file changes after a failure
- Before local commits on a modifying task (final CI binds to committed HEAD)

## Workflow

1. During development use skill `select-and-run-tests` (Levels 0–2).
2. Commit all tracked changes; verify clean working tree.
3. On committed HEAD run full CI **once**:

```bash
scripts/ci.sh
```

4. Verify final evidence:

```bash
python3 scripts/check-ci-evidence.py
```

5. On failure, fix and rerun only the failed check:

```bash
scripts/ci.sh --only ruff.format
```

6. After the fix changes files, commit, verify clean tree, then run one new full CI.

Diagnostic modes (`--only`, `--from`, `--resume-failed`) do **not** count as final CI
evidence. Only `mode=full` with `finalEvidence=true` and `CI_EVIDENCE_RESULT=success`
count.

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
| `packaging.wheel-smoke` | Installed wheel outside checkout |
| `smoke.init` / `smoke.lint` | Temporary project smoke |
| `smoke.tui` | Headless CLI scenarios |

List check ids: `scripts/ci.sh --list-checks`

## Common fixes

| Failure | Action |
|---------|--------|
| Coverage gap | Add behavior tests in existing modules |
| mypy | Fix types in `spell_sync/` |
| Docs style | Remove `---` horizontal rules |
| Agent config | Fix `.cursor/` issues flagged by validator |
| Docs contract | Fix stale claims flagged by validator |

## Stop conditions

- Stop when final `scripts/ci.sh` exits **0** with `finalEvidence=true` and
  `python3 scripts/check-ci-evidence.py` reports `CI_EVIDENCE_RESULT=success`
- Stop and report if a failure requires an architectural decision
- Do not mask failures or weaken coverage gates
- After successful final evidence, do not modify tracked repository files

## Final report

- Focused commands from `select-and-run-tests` (including skipped duplicates)
- Full CI runs attempted and reason for any extra run
- `CI_SUMMARY`, `CI_LOG`, and `CI_EVIDENCE_*` paths/values
- `CI_FAILED_ID` when CI failed

## Finalize workspace snapshot

Modifying tasks only — after `python3 scripts/check-ci-evidence.py` success: skill
`create-code-snapshot` in spell-sync-dev with `--force`, then `--check`; re-verify evidence;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`. SSOT:
`docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
