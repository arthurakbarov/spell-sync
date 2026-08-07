---
name: project-environment
description: >-
  Manage spell-sync maintainer environment lifecycle: bootstrap, sync, check,
  recreate, dependency and Python/uv updates, evidence mismatch, snapshot restoration.
  Run environment check before any Python work.
---

# Project environment

Shared contract: `.cursor/README.md` § Shared contract.

Use before any maintainer Python work (tests, CI, validators, packaging).

## When to use

- Fresh checkout or missing `.venv`
- Environment check failures
- Dependency or Python/uv upgrades
- CI evidence environment mismatch
- Snapshot restoration after archive import

## Do not use

- Raw `uv sync` without `project_environment.py sync` (skips metadata and evidence)
- Ambient Python for environment metadata or CI evidence identity
- Hand-editing `.venv/.spell-sync-environment.json` or `.artifacts/environment/environment.json`
- Mutate owner `.venv` in ordinary unit tests (use `tmp_path` repos)

## Loop (edit)

```bash
python3 scripts/project_environment.py check
# if needed:
python3 scripts/project_environment.py sync
```

Preconditions: `uv` `0.11.21` on PATH; Python `3.14.6`
(`.python-version`, `config/environment-contract.toml`).

## Checkpoint

```bash
python3 scripts/project_environment.py check
python3 scripts/run_dev_loop.py --commit-gate
```

After dependency edits: edit `pyproject.toml` → `uv lock` → `sync` → `check`.

## Full gate (owner push / publish / final only)

```bash
python3 scripts/project_environment.py check
scripts/ci.sh
python3 scripts/check_ci_evidence.py
```

On `ci-evidence.environment-mismatch`: `check` → one full CI at clean HEAD → re-verify.
Do not hand-edit environment evidence JSON.

## Related

```bash
python3 scripts/project_environment.py info
python3 scripts/project_environment.py info --json
python3 scripts/project_environment.py bootstrap --allow-python-download
python3 scripts/project_environment.py recreate
python3 scripts/project_environment.py clean
```

Failure IDs: `environment.venv-stale`, `environment.manual-mutation-detected`,
`environment.venv-python-mismatch`.

Python/uv bump: update contract + `.python-version` → recreate → validators + one full CI.

Snapshot restore from `$HOME/code.zip`: `sync` + `check`; never copy `.venv` from archive.
Modifying-task snapshot: skill `create-code-snapshot` in spell-sync-dev after evidence success.

- CI runs `project_environment.py sync` before `ci_runner.py`
- Tests: `EnvironmentPaths` via `test_environment_paths()` for isolation

