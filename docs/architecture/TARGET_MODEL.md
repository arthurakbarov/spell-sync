# Target model

Spell Sync synchronizes **application custom dictionaries** only. Built-in application
dictionaries are never read or modified.

## Concepts

| Symbol | Meaning |
|--------|---------|
| `W` | Canonical personal wordlist |
| `Cᵢ` | Custom dictionary for enabled target *i* |
| `Bᵢ` | Built-in dictionary (outside Spell Sync) |

Pull: `W' = W ∪ C₁ ∪ … ∪ Cₙ` (union only).

Push: most targets receive full `W`; subset targets apply `filterᵢ(W)` (for example Windows
locale files).

## Discovery

Target discovery lives under `spell_sync/dictionaries/` and `spell_sync/project_setup/`.
Discovery returns DTOs (`SetupTarget`, health views) — not raw filesystem paths in user output.

Config enables targets via `[dictionaries]` boolean keys in `spell-sync.toml`.

## Capability matrix

Public registry: [SUPPORTED_TARGETS.md](../SUPPORTED_TARGETS.md).

Packaged validation metadata: `docs/target-validation.json` (shipped in wheel).

CI synthetic tests prove read/write/discovery code paths — they do **not** replace manual
validation on real applications.

## Validation levels

| Level | Meaning |
|-------|---------|
| implemented | Discovery + read/write code exists |
| automatically tested | CI fixtures against synthetic dictionaries |
| manually validated | Owner-recorded pass on real application version |
| experimental | Partial or unstable real-app coverage |
| not validated | Default until manual pass recorded |

Update manual rows only after owner-approved testing on throwaway profiles. See
[MANUAL_TESTING.md](../MANUAL_TESTING.md).

## Safe read-only checks

These do not mutate real dictionaries:

- `python3 scripts/check_target_capabilities.py --check`
- `spell-sync doctor --targets`
- TUI Targets → Details / automated validation display
- Installed-wheel smoke with synthetic HOME

## Maintainer commands

```bash
python3 scripts/check_target_capabilities.py --check
python3 scripts/check_target_capabilities.py --write   # regenerate bundled JSON when matrix changes
```

Skill: `.cursor/skills/platform-validation/SKILL.md` (maintainer workspace).
