# Supported targets

Spell Sync synchronizes **application custom dictionaries** only. Built-in application
dictionaries are never inspected or modified.

## Meaning of support levels

| Level | Meaning |
|-------|---------|
| **Implemented** | Discovery, read, and write code exists in the public repository. |
| **Automatically tested** | Behavior is covered by synthetic fixtures and automated tests in CI. |
| **Manually validated** | A maintainer ran a real application test on a specific OS and recorded the result in `docs/target-validation.json`. |
| **Experimental** | Implementation exists, but real-app validation is incomplete or known limitations remain. |
| **Not validated** | No real application test has been recorded yet (`manual_validation: not-run`). |

Automatically tested does **not** mean manually validated on your machine or application version.

## Capability matrix

Machine-readable validation data lives in `docs/target-validation.json`. The table below is
generated — do not edit it by hand.

[target-capabilities:start]
Target | OS | Pull | Push | Filtering | Profiles | Close policy | Automated | Manual | Last real-app test
------ | -- | ---- | ---- | --------- | -------- | ------------ | --------- | ------ | ------------------
Brave | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Brave | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Brave | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Chrome | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Chrome | macos | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Chrome | windows | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Edge | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Edge | macos | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Edge | windows | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Editor dictionaries | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Editor dictionaries | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Editor dictionaries | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Firefox | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Firefox | macos | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Firefox | windows | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Hunspell | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Hunspell | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Hunspell | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
JetBrains | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
JetBrains | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
JetBrains | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
LibreOffice | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
LibreOffice | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
LibreOffice | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
macOS Spelling | macos | Yes | Yes | full | system-managed | not-required | pass | not-run | —
Neovim | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Neovim | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Neovim | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Obsidian | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Obsidian | macos | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Obsidian | windows | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Vivaldi | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Vivaldi | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Vivaldi | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Windows Spelling | windows | Yes | Yes | locale-specific | system-managed | not-required | pass | not-run | —
[target-capabilities:end]

Run `python3 scripts/check_target_capabilities.py --write` to regenerate after updating
validation data.

## Platform validation status

All entries currently have `manual_validation: not-run` unless explicitly updated with real
evidence (application version and test date). Synthetic CI tests provide `automated_validation:
pass` only.

## Known limitations

- Windows locale custom dictionaries (`win_spelling`) apply language-specific subset filtering.
- Chrome, Edge, Firefox, and Obsidian Push may skip dictionaries while the application is running.
- macOS and Windows system spelling targets are platform-specific and not available on all OSes.
- Real spell-checker behavior beyond custom dictionary writes is not guaranteed.
- Adversarial internal-artifact suite R1–R7 is exercised with POSIX symlink/hard-link vectors in
  CI. Windows reparse points and junctions are not covered by a real-hardware adversarial suite;
  treat Windows as capability-limited for that threat model (see [Supported environments](SUPPORTED_ENVIRONMENTS.md)).
- Real-application manual validation is recorded in `docs/target-validation.json` and may be
  `not-run` for every target/OS row even when automated synthetic tests pass.

## How to contribute a manual test result

1. Follow the `platform-validation` Cursor skill in `.cursor/skills/platform-validation/`.
2. Use a dedicated throwaway profile when possible and obtain owner permission before mutating real dictionaries.
3. Record results in `docs/target-validation.json` with `application_version`, `tested_on`, and repository-relative `evidence`.
4. Run `python3 scripts/check_target_capabilities.py --write` and `scripts/ci.sh`.

Do not mark manual pass without a real test date and application version.
