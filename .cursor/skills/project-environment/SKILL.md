---
name: project-environment
description: >-
  Manage spell-sync maintainer environment lifecycle: bootstrap, sync, check,
  recreate, dependency and Python/uv updates, evidence mismatch, snapshot restoration.
  Run environment check before any Python work.
---

# Project environment

Use this skill before any maintainer Python work (tests, CI, validators, packaging).

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

## Preconditions

- `uv` on PATH at contract-pinned version (`0.11.21`)
- Canonical maintainer Python `3.12.13` (see `.python-version` and `config/environment-contract.toml`)

## Commands (in order)

### info

Inspect current state without mutation:

```bash
python scripts/project_environment.py info
python scripts/project_environment.py info --json
```

### bootstrap

First-time Python install (maintainer machine only):

```bash
python scripts/project_environment.py bootstrap --allow-python-download
```

### sync (canonical)

**Always** use this instead of raw `uv sync`:

```bash
python scripts/project_environment.py sync
```

Performs: `uv lock --check` → `uv sync` → `.venv` probe → metadata → `check` → environment evidence.

### check (read-only)

```bash
python scripts/project_environment.py check
```

Failure IDs:

| ID | Meaning |
|----|---------|
| `environment.venv-stale` | Declaration/metadata drift |
| `environment.manual-mutation-detected` | Extra/missing/wrong distribution |
| `environment.venv-python-mismatch` | Wrong `.venv` Python patch |

### recreate / clean

```bash
python scripts/project_environment.py recreate   # delete .venv, sync
python scripts/project_environment.py clean    # delete .venv + environment evidence
```

## Dependency mutation workflow

1. Edit `pyproject.toml` / groups
2. `uv lock` (commit `uv.lock`)
3. `python scripts/project_environment.py sync`
4. `python scripts/project_environment.py check`
5. Run focused tests, then pre-final

## Python or uv update

1. Update `config/environment-contract.toml`, `.python-version`, `[tool.uv] required-version`
2. Regenerate lock if needed
3. `python scripts/project_environment.py recreate`
4. Validators + full CI (one final run at exact HEAD)

## Evidence mismatch

If `check-ci-evidence.py` reports `ci-evidence.environment-mismatch`:

1. `python scripts/project_environment.py check`
2. If check passes, re-run full CI once at clean exact HEAD
3. Re-verify: `python scripts/check-ci-evidence.py`

Do not hand-edit `.artifacts/environment/environment.json` or `.venv/.spell-sync-environment.json`.

## Snapshot restoration

After importing owner archive from **`$HOME/code.zip`** (canonical location only):

1. Confirm snapshot manifest `environment` block matches extracted declarations
2. `python scripts/project_environment.py sync` (fresh `.venv` from lock)
3. `python scripts/project_environment.py check`
4. Do **not** copy `.venv` from archive (excluded by policy)

## Modifying-task snapshot finalization

After final CI and `python scripts/check-ci-evidence.py` success:

```bash
python3 "$SPELL_SYNC_DEV/scripts/create-code-snapshot.py" \
  --workspace "$HOME/code" \
  --output "$HOME/code.zip" \
  --force
python3 "$SPELL_SYNC_DEV/scripts/create-code-snapshot.py" \
  --workspace "$HOME/code" \
  --output "$HOME/code.zip" \
  --check
```

Do **not** write `code.zip` under the workspace tree. Report footer uses resolved `$HOME/code.zip`
only. See `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.

## Integration points

- CI: workflow runs `project_environment.py sync` before `ci_runner.py`
- Execution control: workload identity includes `environmentSignature`
- CI summary schema v5: `environmentFingerprintBefore/After` must match
- Tests: pass `EnvironmentPaths` from `test_environment_paths()` for isolation

## Do not

- Run raw `uv sync` then `check` without sync subcommand (metadata/evidence missing)
- Use ambient `python`/`platform.*` for environment evidence
- Mutate owner `.venv` in ordinary unit tests (use `tmp_path` repos)
