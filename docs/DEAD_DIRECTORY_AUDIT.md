# Dead directory audit

Report-only inventory for the maintainer workspace (`~/code/`). **No paths were deleted**
during this audit. Generated on 2026-07-31 at Phase 9 of the 0.3 architecture migration.

Scope: `spell-sync` (public), `spell-sync-dev` (maintainer), `spell-words` (private data),
and the canonical snapshot archive `$HOME/code.zip`.

## Method

- Top-level and well-known generated paths per repository
- Aggregated `__pycache__` trees outside `.venv` in spell-sync
- Git tracked / ignored / untracked classification via `git check-ignore` and `git ls-files`
- No `rm`, `git clean`, or destructive commands executed

## Safe generated cleanup

May be removed; CI and local tooling recreate them automatically.

| Repository | Path | Files | Size | Git | Recreation |
|------------|------|------:|-----:|-----|------------|
| spell-sync | `.coverage` | 1 | 0.8 MiB | ignored | next pytest with coverage |
| spell-sync | `.mypy_cache/` | 19 | 10.7 MiB | ignored | next `mypy spell_sync` |
| spell-sync | `.pytest_cache/` | 6 | 0.2 MiB | ignored | next pytest run |
| spell-sync | `.ruff_cache/` | 50 | 0.1 MiB | ignored | next ruff run |
| spell-sync | `**/__pycache__/` (18 dirs, excl. `.venv`) | 865 | 12.2 MiB | ignored | next Python import |
| spell-sync | `.DS_Store` (multiple) | — | <0.1 MiB | ignored | Finder recreates |
| spell-sync-dev | `.pytest_cache/` | 5 | <0.1 MiB | untracked | next pytest run |
| spell-sync-dev | `.ruff_cache/` | 4 | <0.1 MiB | untracked | next ruff run |
| spell-sync-dev | `.DS_Store` | 1 | <0.1 MiB | ignored | Finder recreates |
| spell-words | `.DS_Store` | 1 | <0.1 MiB | ignored | Finder recreates |

Not present at audit time (no action needed): `build/`, `dist/`, `htmlcov/`, `*.egg-info/`,
`spell_sync.egg-info/`, `UNKNOWN.egg-info/`.

Example manual cleanup (owner discretion, spell-sync only):

```bash
cd spell-words/spell-sync
rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
find spell_sync tests scripts -type d -name __pycache__ -prune -exec rm -rf {} +
```

## Obsolete after workflow removal

| Repository | Path | Status at audit |
|------------|------|-----------------|
| spell-sync-dev | `review-bundles/` | **Absent** — removed in Phase 1 |
| spell-sync-dev | `scripts/review_bundle*.py` | **Absent** — removed in Phase 1 |
| public spell-sync | review-archive workflow | **Absent** — removed in Phase 2C |

No obsolete directories require cleanup.

## Likely stale — owner decision

| Item | Notes | Recommendation |
|------|-------|----------------|
| spell-sync-dev `spell-sync-source.zip` | Legacy gitignored source export (~191 KiB) | Owner decision: delete if superseded by `$HOME/code.zip` |
| spell-sync-dev `.pytest_cache/`, `.ruff_cache/` | Untracked in maintainer repo (no Python package CI there) | Safe to delete |
| macOS `.DS_Store` under `.git/` | Ignored noise | Optional cleanup outside tracked files |

No duplicate nested spell-sync clones, old backup trees, or orphan `build/` / `dist/` trees
were found under `~/code/`.

## Keep (active or intentional)

| Repository | Path | Role |
|------------|------|------|
| spell-sync | `.venv/` | Active maintainer virtualenv (~205 MiB incl. deps) |
| spell-sync | `.artifacts/` | CI evidence, environment contract, execution history (retained for snapshot) |
| spell-sync | `.cursor/`, `.github/` | Tracked agent and CI configuration |
| spell-sync | `.spell-sync.lock` | Ignored local operation lock when present |
| spell-words | `spell-sync/` | Authoritative nested public clone (~205 MiB) |
| workspace | `$HOME/code.zip` | Canonical maintainer snapshot (15.6 MiB at audit); not in git tree |
| all repos | `.git/` | Repository metadata |

## Stashes and locks

| Repository | Git stashes | Notes |
|------------|------------:|-------|
| spell-sync | 0 | Clean |
| spell-sync-dev | 0 | Clean |
| spell-words | 0 | Clean |

## Evidence references

- Snapshot policy excludes `.venv/`, caches, and raw CI logs: `spell-sync-dev/snapshot-policy.toml`
- Retained artifacts bound into `$HOME/code.zip`: `ci-summary.json`, `environment.json`, optional execution summary
- Phase 1 removed review-bundle tooling from spell-sync-dev

## Recommended next steps (manual, optional)

1. Delete safe-generated caches before a snapshot if disk space matters (~24 MiB recoverable in spell-sync caches alone).
2. Do **not** delete `.artifacts/` until CI evidence is refreshed and snapshot policy satisfied.
3. Do **not** delete `spell-words/spell-sync/` or `.venv/` without running `project_environment.py sync` afterward.
