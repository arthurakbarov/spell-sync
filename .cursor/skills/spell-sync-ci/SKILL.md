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

0. Ensure project environment is valid **before** Python work:

```bash
python3 scripts/project_environment.py check
```

If missing `.venv` or metadata, run `python3 scripts/project_environment.py sync` (not raw `uv sync`).
See skill `project-environment`.

1. During development use skill `select-and-run-tests` (Levels 0–2).
2. Commit all tracked changes; verify clean working tree.
3. Assess necessity:

```bash
python3 scripts/check_ci_necessity.py --explain
```

4. When `CI_NECESSITY_RESULT=full-required`, run full CI **once** on committed HEAD through
   the execution controller (integrated in `ci_runner.py`):

```bash
scripts/ci.sh
```

Do not pipe CI through `tail`, `tee`, or other wrappers — hard bounds and
`CI_TIMEOUT_CHECK_ID` depend on direct runner output.

5. When `CI_NECESSITY_RESULT=lightweight-sufficient`:

```bash
python3 scripts/run_lightweight_validation.py
```

6. Verify final evidence:

```bash
python3 scripts/check_ci_evidence.py
```

Expect `CI_EVIDENCE_MATCH=exact-head` or `CI_EVIDENCE_MATCH=reused-non-ci-change`.

7. On failure, fix and rerun only the failed check:

```bash
scripts/ci.sh --only ruff.format
```

8. After the fix changes CI-relevant files, commit, verify clean tree, reassess necessity, then run one new full CI when required.

Diagnostic modes (`--only`, `--from`, `--resume-failed`) do **not** count as final CI
evidence. Only `mode=full` with `finalEvidence=true` and `CI_EVIDENCE_RESULT=success`
count.

Release, publication, and signed artifact workflows require exact-head evidence:

```bash
python3 scripts/check_ci_evidence.py --release
```

## What ci.sh enforces

`scripts/ci.sh` is the single CI entry point (via `scripts/ci_runner.py`). Gate ids are
not duplicated here — list the current set with:

```bash
scripts/ci.sh --list-checks
```

Grouped coverage typically includes docs style/contract, agent config, architecture and
target capability checks, ruff, mypy, grouped pytest with coverage policy, packaging
(build/twine/wheel-smoke), and headless smoke scenarios. Treat `--list-checks` as SSOT
for exact check ids.

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
  `python3 scripts/check_ci_evidence.py` reports `CI_EVIDENCE_RESULT=success`
- Stop and report if a failure requires an architectural decision
- Do not mask failures or weaken coverage gates
- After successful final evidence, do not modify tracked repository files

## Final report

- Focused commands from `select-and-run-tests` (including skipped duplicates)
- Full CI runs attempted and reason for any extra run
- `CI_SUMMARY`, `CI_LOG`, and `CI_EVIDENCE_*` paths/values
- `CI_FAILED_ID` when CI failed

## Finalize workspace snapshot

Modifying tasks only — after successful `python3 scripts/check_ci_evidence.py`:
skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
re-verify evidence and clean trees; canonical `$HOME/code.zip`; report §14 and
footer `CODE_ARCHIVE` / `SHA256`. SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
