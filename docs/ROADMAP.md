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
| R-PWR | Shrink legacy coverage-padding inventory over time | Hygiene only; frozen ceiling |

## Not on this roadmap

- Architecture phases 1–10 (complete)
- Post-0.3 engineering ops (complete)
- Copying nix-darwin hosts/sops/flake/owner nx TUI

When an item above is finished, remove its row and refresh PRODUCT_COMPLETION /
FEATURE_MATRIX in the same change.
