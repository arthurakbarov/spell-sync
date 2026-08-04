# Dead directory audit

Report-only inventory of **generated and obsolete paths inside this public repository**.
**No paths were deleted** during this audit. Generated on 2026-07-31 at Phase 9 of the 0.3
architecture migration; factual claims refreshed 2026-08-04.

Maintainer-only workspace layout and private tooling live outside this repository and are not
inventoried here.

## Method

- Top-level and well-known generated paths in `spell-sync`
- Aggregated `__pycache__` trees outside `.venv`
- Git tracked / ignored / untracked classification via `git check-ignore` and `git ls-files`
- No `rm`, `git clean`, or destructive commands executed

## Safe generated cleanup

May be removed; CI and local tooling recreate them automatically.

| Path | Git | Recreation |
|------|-----|------------|
| `.coverage` | ignored | next pytest with coverage |
| `.mypy_cache/` | ignored | next `mypy spell_sync` |
| `.pytest_cache/` | ignored | next pytest run |
| `.ruff_cache/` | ignored | next ruff run |
| `**/__pycache__/` (excl. `.venv`) | ignored | next Python import |
| `.DS_Store` | ignored | Finder recreates |

Not present at audit time (no action needed): `build/`, `dist/`, `htmlcov/`, `*.egg-info/`.

Example manual cleanup (owner discretion):

```bash
rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
find spell_sync tests scripts -type d -name __pycache__ -prune -exec rm -rf {} +
```

## Obsolete after workflow removal

| Path / topic | Status |
|--------------|--------|
| Public review-archive workflow (`scripts/review[-_]archive*`) | **Absent** — tracked sources removed in Phase 2C; untracked bytecode remnants may remain until local `__pycache__` cleanup |

Maintainer review-bundle directories and scripts are out of scope for this public audit.

## Keep (active or intentional)

| Path | Role |
|------|------|
| `.venv/` | Disposable maintainer virtualenv (ignored, not snapshotted) |
| `.artifacts/` | CI evidence and environment contract (retained for snapshot policy) |
| `.cursor/`, `.github/` | Tracked agent and CI configuration |
| `.spell-sync.lock` | Ignored local operation lock when present |
| `.git/` | Repository metadata |

## Stashes

At the Phase 9 audit and the 2026-08-04 refresh: Git stash list was empty.

## Recommended next steps (manual, optional)

1. Delete safe-generated caches before a snapshot if disk space matters.
2. Do **not** delete `.artifacts/` until CI evidence is refreshed and snapshot policy satisfied.
3. Recreate `.venv/` only via `python3 scripts/project_environment.py sync` (or bootstrap).
