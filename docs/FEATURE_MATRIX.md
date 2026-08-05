# Feature honesty matrix

Coverage honesty for Spell Sync product surfaces. Values: **complete**, **partial**,
**missing**, **not-applicable**, **blocked**.

**Complete** means automated gates exist and pass in full CI on a healthy checkout. It does
**not** mean real-application acceptance on every OS or interactive TUI smoke on every host.

State vocabulary: [CONTRACTS.md](CONTRACTS.md). Per-target rows: [SUPPORTED_TARGETS.md](SUPPORTED_TARGETS.md)
and `docs/target-validation.json`. Residuals: [PRODUCT_COMPLETION.md](PRODUCT_COMPLETION.md),
[ROADMAP.md](ROADMAP.md).

| Feature | Policy / code | Unit / module | Safety cluster | Full CI | Doctor / status | Real-app manual | Interactive acceptance | Docs | Known blockers |
|---------|---------------|---------------|----------------|---------|-----------------|-----------------|------------------------|------|----------------|
| Pull | complete | complete | complete | complete | partial | missing | missing | complete | Manual mutation samples open (R-CON) |
| Push | complete | complete | complete | complete | partial | partial | missing | complete | chrome/macos dry-run only; Firefox+ mutation open |
| Recovery | complete | complete | complete | complete | partial | missing | missing | complete | Real crash mid-write samples not recorded |
| Project setup / init | complete | complete | not-applicable | complete | partial | missing | missing | complete | Second-machine path presets not field-tested |
| Target settings | complete | complete | partial | complete | partial | missing | missing | complete | Real toggles on primary profiles deferred |
| Doctor / status | complete | complete | not-applicable | complete | complete | partial | not-applicable | complete | Host-specific drift varies |
| TUI flows | complete | complete | partial | complete | not-applicable | missing | missing | complete | Headless tests only; no recorded interactive acceptance |
| Target matrix (all apps) | complete | complete | partial | complete | partial | partial | missing | complete | Most `manual_validation: not-run` |
| Packaging / wheel | complete | complete | not-applicable | complete | not-applicable | missing | not-applicable | complete | Installed-wheel outside checkout before publish |
| Agent / edit loop | complete | complete | not-applicable | complete | not-applicable | not-applicable | not-applicable | complete | Sample fill uses budget; not a coverage wall |
| Windows adversarial (R-WIN) | partial | partial | partial | partial | not-applicable | blocked | blocked | complete | Not runnable on maintainer macOS host |
| Coverage padding (R-PWR) | partial | partial | not-applicable | complete | not-applicable | not-applicable | not-applicable | complete | Frozen inventory; shrink only |

## Notes

### Pull / Push / Recovery

- Safety clusters (`pull`, `push`, `transaction`, `recovery`) are required at commit gate when
  those paths change.
- Product mutations are never wrapped by the execution controller.
- Preview and confirm share one immutable prepared object; stale plan IDs must not execute.

### Real-app manual and interactive acceptance (R-CON)

- **Real-app manual**: recorded in `docs/target-validation.json` via skill `platform-validation`
  (schema: `docs/technical/target-validation.schema.json`;
  `python3 scripts/validate_target_validation_schema.py`).
- **Interactive acceptance**: human GUI/TUI confirmation on a real machine (separate from
  headless tests). Still mostly missing; do not equate headless TUI tests with interactive.
- Current samples (2026-08-05): chrome/macos and macos_spelling/macos, read-only / dry-run.
- Do not claim Push "works on Chrome" without distinguishing dry-run from mutation.

### Doctor / status

- Point-in-time probes. Exit 0 is not permanent health ([CONTRACTS.md](CONTRACTS.md)).
- `--health-check` elevates required actions to exit 2.
- JSON shape: `docs/technical/doctor-report.schema.json` +
  `python3 scripts/validate_doctor_schema.py`.

### How to use this table

- Before claiming a feature "works", check Real-app manual **and** Interactive acceptance.
- Prefer closing R-CON samples over growing legacy coverage padding (R-PWR).
- Update this table when support matrix, residuals, or safety clusters change.
