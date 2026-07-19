---
name: add-target
description: >-
  Add support for a new application custom dictionary target. Use when adding
  discovery, reader, writer, or config entry for a supported application.
  Custom dictionaries only — never built-in dictionary inspection.
---

# Add target

## When to use

- New application or dictionary format support
- New target identifier in discovery and config schema

## Do not use

- To add built-in dictionary inspection or language-pack discovery
- To force-enable corrupt, unreadable, or unsupported targets

## Checklist

### Identity and scope

- [ ] Target identifier and display name
- [ ] Custom dictionary only — built-in dictionaries not read or written
- [ ] Supported OS/platform documented

### Discovery and I/O

- [ ] Discovery paths and profile handling
- [ ] Reader preserves encoding, newlines, checksum/format where required
- [ ] Writer preserves format semantics
- [ ] Corrupt and unreadable states surfaced (not force-enabled)

### Sync behavior

- [ ] Pull: union into canonical wordlist
- [ ] Push: full wordlist or documented subset filter
- [ ] Application-running policy respected
- [ ] Transaction participation and Recovery behavior
- [ ] Snapshots before writes

### Quality

- [ ] Synthetic fixtures in tests — no real application dictionaries
- [ ] Platform limitations stated when simulated
- [ ] Public docs updated (`docs/CONFIGURATION.md`, product copy if user-visible)
- [ ] Installed-wheel resource check if bundled paths involved
- [ ] `spell_sync/target_capabilities.py` descriptor added or updated
- [ ] `docs/target-validation.json` row(s) for each supported platform
- [ ] Regenerate matrix: `python3.11 scripts/check-target-capabilities.py --write`
- [ ] Contract tests in `tests/test_target_capabilities.py`
- [ ] Manual validation status explicit (`not-run` until real-app evidence exists)

## Pre-read

- `spell_sync/dictionaries.py`, `spell_sync/paths.py`
- Existing target implementation as template
- `@docs/ARCHITECTURE.md` — subset filtering section

## Stop conditions

- All applicable checklist items complete
- Focused tests + safety suites green
- No built-in dictionary support added

## Final report

- Target identifier and platforms
- Discovery paths
- Pull/Push/subset semantics
- Tests and docs updated
