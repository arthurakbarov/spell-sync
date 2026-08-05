# Dead directory audit

Inventory of **generated and obsolete paths inside this public repository**.
Cleanup of safe generated paths was executed 2026-08-05. Tracked product dead-code
scan (`scripts/audit_dead_code.py`) reported **0 candidates** the same day.

Maintainer-only workspace layout and private tooling live outside this repository and are not
inventoried here.

## Method

- Top-level and well-known generated paths in `spell-sync`
- Aggregated `__pycache__` trees outside `.venv`
- Git tracked / ignored / untracked classification via `git check-ignore` and `git ls-files`
- Product tiny-module scan: `python3 scripts/audit_dead_code.py`
- Broader import/reference heuristics over `spell_sync/` + `tests/` + `scripts/` (no tracked
  unreferenced modules found; nested relative imports are live)
- `ruff` unused-import scan (`F401`/`F841`) on `spell_sync/`: clean
- test-impact path existence: all mapped production/test/validator paths present

## Safe generated cleanup

May be removed; CI and local tooling recreate them automatically.

| Path | Git | Status 2026-08-05 |
|------|-----|-------------------|
| `.coverage` | ignored | **deleted** |
| `.mypy_cache/` | ignored | **deleted** |
| `.pytest_cache/` | ignored | **deleted** |
| `.ruff_cache/` | ignored | **deleted** |
| `.hypothesis/` | ignored | **deleted** |
| `**/__pycache__/` (excl. `.venv`) | ignored | **deleted** |
| `.DS_Store` | ignored | **deleted** |

Not present (no action needed): `build/`, `dist/`, `htmlcov/`, `*.egg-info/`.

Recreate caches by running normal checks; recreate `.venv/` only via
`python3 scripts/project_environment.py sync` (or bootstrap).

## Obsolete after workflow removal

| Path / topic | Status |
|--------------|--------|
| Public review-archive workflow (`scripts/review[-_]archive*`) | **Absent** |
| `docs/UX_0_2_IMPLEMENTATION.md` | **Absent** |
| `docs/platform-validation-readiness.md` | **Absent** |

Maintainer review-bundle directories and scripts are out of scope for this public audit.

## Tracked dead code

| Check | Result |
|-------|--------|
| `scripts/audit_dead_code.py` | `DEAD_CODE_AUDIT_RESULT=success`, 0 candidates |
| Unreferenced public top-level defs (heuristic) | 0 |
| Broken `spell_sync.*` imports from tests | 0 |
| Missing `tests/test-impact.toml` paths | 0 |
| Untracked non-ignored files | none |

No tracked source, test, or doc files were deleted: nothing qualified as dead.

## Keep (active or intentional)

| Path | Role |
|------|------|
| `.venv/` | Disposable maintainer virtualenv (ignored, not snapshotted) |
| `.artifacts/` | CI evidence and environment contract (retained for snapshot policy) |
| `.cursor/`, `.github/` | Tracked agent and CI configuration |
| `.spell-sync.lock` | Ignored local operation lock when present |
| `.git/` | Repository metadata |
| ADRs under `docs/decisions/` | Linked from architecture docs index |
| `docs/technical/TARGET_SUPPORT_MATRIX.md` | Referenced from test-impact / support matrix tooling |

## Stashes

Git stash list empty at cleanup time.

## Recommended next steps

1. Re-run `python3 scripts/audit_dead_code.py` after large product deletions.
2. Do **not** delete `.artifacts/` until CI evidence is refreshed and snapshot policy satisfied.
3. Shrink legacy coverage-padding tests only under residual R-PWR policy (not bulk-deleted here).
