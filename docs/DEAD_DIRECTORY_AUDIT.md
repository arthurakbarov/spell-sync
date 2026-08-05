# Dead directory audit

Policy for **generated and obsolete paths inside this public repository**.
Re-run the product tiny-module scan after large deletions:

```bash
python3 scripts/audit_dead_code.py
```

Maintainer-only workspace layout and private tooling live outside this repository and are not
inventoried here.

## Method

- Top-level and well-known generated paths in `spell-sync`
- Aggregated `__pycache__` trees outside `.venv`
- Git tracked / ignored / untracked classification via `git check-ignore` and `git ls-files`
- Product tiny-module scan: `python3 scripts/audit_dead_code.py`
- Broader import/reference heuristics over `spell_sync/` + `tests/` + `scripts/`
- `ruff` unused-import scan (`F401`/`F841`) on `spell_sync/`
- test-impact path existence for mapped production/test/validator paths

## Safe generated cleanup

May be removed locally; CI and local tooling recreate them automatically. They are listed in
`.gitignore` and must not be committed.

| Path | Notes |
|------|-------|
| `.coverage` | Coverage data file |
| `.mypy_cache/` | mypy cache |
| `.pytest_cache/` | pytest cache |
| `.ruff_cache/` | ruff cache |
| `.hypothesis/` | hypothesis examples |
| `**/__pycache__/` (excl. `.venv`) | Bytecode |
| `.DS_Store` | macOS folder metadata |
| `build/`, `dist/`, `htmlcov/`, `*.egg-info/` | Packaging / HTML coverage (absent unless built) |

Recreate caches by running normal checks; recreate `.venv/` only via
`python3 scripts/project_environment.py sync` (or bootstrap).

## Obsolete after workflow removal

These paths must remain absent from the public tree (guards / history, not live code):

| Path / topic | Expected status |
|--------------|-----------------|
| Public review-archive workflow (`scripts/review[-_]archive*`) | Absent |
| `docs/UX_0_2_IMPLEMENTATION.md` | Absent |
| `docs/platform-validation-readiness.md` | Absent |

Maintainer review-bundle directories and scripts are out of scope for this public audit.

## Tracked dead code

| Check | Result |
|-------|--------|
| `scripts/audit_dead_code.py` | Expect `DEAD_CODE_AUDIT_RESULT=success` with 0 small-file candidates |
| Unreferenced public top-level modules | Expect 0 |
| Broken `spell_sync.*` imports from tests | Expect 0 |
| Missing `tests/test-impact.toml` paths | Expect 0 |
| Untracked non-ignored files | Expect none |

Symbol-level leftovers (unused helpers/constants) are removed when found; this audit does not
claim a permanent zero for every private alias.

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

`git stash list` must be empty at task end (agent workflow).

## Recommended next steps

1. Re-run `python3 scripts/audit_dead_code.py` after large product deletions.
2. Do **not** delete `.artifacts/` until CI evidence is refreshed and snapshot policy satisfied.
3. Shrink legacy coverage-padding tests only under residual R-PWR policy (not bulk-deleted here).
