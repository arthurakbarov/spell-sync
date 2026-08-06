# Roadmap

Only items that still fail a completion criterion. Done-definitions:
[PRODUCT_COMPLETION.md](PRODUCT_COMPLETION.md),
[ENGINEERING_COMPLETION.md](ENGINEERING_COMPLETION.md). Honesty:
[FEATURE_MATRIX.md](FEATURE_MATRIX.md).

| ID | Item | Blocks |
|----|------|--------|
| owner-publish | Explicit owner tag / GitHub Release / package publish after preflight | Product criterion 10 |
| R-CON | More real-app manual samples (Firefox + mutation; other OSes) | Publish confidence, not engineering done |
| R-WIN | Windows hardware adversarial R1–R7 | Windows threat-model claim |
| R-PWR | Shrink legacy coverage-padding inventory over time (≤371 defs / ≤53 bare) | Hygiene only; frozen ceiling |
| R-DUR | Physical power-loss / journal fsync durability proof | Durability claim beyond process-crash |

## Not on this roadmap

- Architecture phases 1–10 (complete)
- Post-0.3 engineering ops (complete)
- Copying nix-darwin hosts/sops/flake/owner nx TUI
- **Full gitleaks (or similar) CI scanner** — end users never see it; agents already have
  lean `scan_privacy_tree` + `packaging.members`. Extra scanner deps and false-positive
  policy are owner tooling choice, not a product or agent-done gap.
- **`subsystems.json` inventory from scratch** — would duplicate
  [`PROJECT_MAP.md`](PROJECT_MAP.md) / architecture docs without helping a non-technical
  user or clarifying agent ownership beyond the existing map.
- **Unified generated-docs pipeline** — fences already exist
  (`dev-commands`, `ci-checks`, target-capabilities). A meta-generator is tooling
  architecture, not a missing user or agent capability.

When an item above is finished, remove its row and refresh PRODUCT_COMPLETION /
FEATURE_MATRIX in the same change.
