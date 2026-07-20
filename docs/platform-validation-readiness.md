# Platform validation readiness — Spell Sync 0.2.1

This report records what can be verified **without** claiming real-application manual
validation. Automated CI fixtures, installed-wheel smoke tests, and read-only detection
do **not** satisfy `manual_validation: pass`.

## Current environment

| Field | Value |
|-------|-------|
| Host OS | macOS 26.5.2 (arm64) |
| Spell Sync version | 0.2.1 |
| Validation host date | 2026-07-20 |

## Detected applications (read-only)

Read-only `doctor --targets` on this host found dictionary paths for:

| Target family | Detection | Notes |
|---------------|-----------|-------|
| macOS Spelling | detected | system dictionary present |
| macOS AppleSpell group container | detected | unreadable (expected sandbox) |
| Sublime Text | detected | SpellSync package settings |
| Cursor editor dictionary | detected | spell-sync-words.txt |
| VS Code editor dictionary | not detected | path missing on this host |
| Google Chrome (Default profile) | detected | Custom Dictionary.txt |
| Neovim Hunspell (en) | detected | .add dictionary |

Application **version strings were not recorded** in this readiness pass. Real manual
validation requires explicit version capture per target.

## Throwaway profiles

| Check | Status |
|-------|--------|
| Dedicated throwaway browser profile available | unknown — not confirmed |
| Dedicated throwaway editor profile available | unknown — not confirmed |
| Owner permission for real dictionary mutation | **not granted** in this task |

Without owner-approved throwaway profiles, Pull/Push execution against production profiles
remains blocked.

## Blockers for manual `pass`

1. No owner permission to mutate real application dictionaries on this machine.
2. No recorded `application_version`, `tested_on`, or redacted evidence for any target.
3. No full Pull preview → Pull execution → Push preview → Push execution cycle on a
   throwaway profile.
4. Linux and Windows matrix rows cannot be validated from this macOS host.

## Safe checks (no dictionary mutation)

These may run without changing real dictionaries:

- `scripts/check-target-capabilities.py --check`
- packaged `target-validation.json` in installed wheel
- **Targets → Details** / `target_details` automated validation display
- read-only `doctor --targets`
- synthetic HOME installed-wheel workflow (unit / integration tests)
- support report and session report export with synthetic project directories

## Actions requiring owner permission

- executing Pull or Push against real application dictionaries
- adding or removing test words in personal wordlist or real dictionaries
- using the primary browser or editor profile for validation
- recording `manual_validation: pass` in `docs/target-validation.json`
- publishing validation evidence that includes paths, config, or words

## Manual validation matrix status

All **35** target/platform combinations in `docs/target-validation.json` remain:

```text
manual_validation: not-run
```

No row was upgraded to `pass`, `fail`, or `experimental` during this readiness review.

## Evidence levels (unchanged)

| Level | Meaning on this host |
|-------|----------------------|
| implemented | all public targets have discovery/read/write code |
| automatically tested | CI synthetic fixtures — **yes** for public repo |
| manually validated | **none** recorded |
| experimental | none marked |
| not validated | all 35 rows (`not-run`) |

## Next steps (when owner approves)

1. Create or select throwaway profiles per target family.
2. Follow `.cursor/skills/platform-validation/SKILL.md`.
3. Record redacted results in `docs/target-validation.json` with exact application versions.
4. Regenerate docs: `python3.11 scripts/check-target-capabilities.py --write`.
