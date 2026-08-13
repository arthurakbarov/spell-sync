# Supported apps

Spell Sync works with **custom dictionaries** in supported applications. It never reads or
changes **built-in** dictionaries shipped with an app.

## First-run defaults

When setup finds a readable custom dictionary on your computer, that target is
**on by default**. You can turn targets off under **Targets** during or after setup.

Examples of what “found” usually means:

| App area | Target id | Notes |
|----------|-----------|-------|
| Chrome / Edge / Brave / Vivaldi | `chrome`, `edge`, … | Chromium custom dictionary files |
| Firefox | `firefox` | `persdict.dat` profiles |
| Editors (VS Code / Cursor family) | `editors` | Shared `spell-sync-words.txt` |
| Sublime Text | `sublime` | Spell Sync package preferences (see [Sublime Text](#sublime-text)) |
| Neovim | `neovim` | `.add` spell files |
| JetBrains IDEs | `jetbrains` | IDE custom dictionaries |
| Obsidian | `obsidian` | Obsidian custom dictionary |
| LibreOffice | `libreoffice` | User dictionary |
| Hunspell | `hunspell` | User `.dic` files |
| macOS Spelling | `macos_spelling` | System custom words (Safari, Notes, and other AppleSpell clients) |
| Windows Spelling | `win_spelling` | Locale custom spelling files (Windows only) |

## Quick answer: will this work with my app?

If the app lets you add personal words to a custom dictionary, Spell Sync may support it when
it appears in **Targets**. Run **Check my apps** to see what was found on your computer.

## Categories

- **Browsers** — custom spelling lists where the browser stores user-added words
- **Editors and IDEs** — project or user dictionary files
- **Writing apps** — application-specific custom word lists
- **System spelling** — OS custom dictionary locations where supported
- **Hunspell-compatible tools** — custom `.dic` lists you maintain

## For each target

Open **Targets** in Spell Sync for your installation. The screen shows:

- Whether the target is enabled
- Whether Spell Sync found the custom dictionary
- Whether the app should be closed before Update

## First-time tip

If nothing is found, open the app once and add **one custom word**, then run **Check my apps**
again. For Sublime Text, prefer adding that first word via Spell Sync (or `wordlist.txt`)
rather than Sublime’s “Add to dictionary” — see [Sublime Text](#sublime-text).

## Meaning of support levels

| Level | Meaning |
|-------|---------|
| **Implemented** | Discovery, read, and write code exists in the public repository. |
| **Automatically tested** | Behavior is covered by synthetic fixtures and automated tests in CI. |
| **Manually validated** | A real application test was recorded for a specific OS in `docs/technical/target-validation.json`. |
| **Experimental** | Implementation exists, but real-app validation is incomplete or known limitations remain. |
| **Not validated** | No real application test has been recorded yet (`manual_validation: not-run`). |

Automatically tested does **not** mean manually validated on your machine or application version.

## Capability matrix

Machine-readable validation data lives in `docs/technical/target-validation.json`. The table below is
generated — do not edit it by hand.

<!-- target-capabilities:start -->
Target | OS | Pull | Push | Filtering | Profiles | Close policy | Automated | Manual | Last real-app test
------ | -- | ---- | ---- | --------- | -------- | ------------ | --------- | ------ | ------------------
Brave | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Brave | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Brave | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Chrome | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Chrome | macos | Yes | Yes | full | multi-profile | block-if-running | pass | pass | 2026-08-08
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
macOS Spelling | macos | Yes | Yes | full | system-managed | not-required | pass | pass | 2026-08-05
Neovim | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Neovim | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Neovim | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Obsidian | linux | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Obsidian | macos | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Obsidian | windows | Yes | Yes | full | multi-profile | block-if-running | pass | not-run | —
Sublime Text | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Sublime Text | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Sublime Text | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Vivaldi | linux | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Vivaldi | macos | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Vivaldi | windows | Yes | Yes | full | multi-profile | not-required | pass | not-run | —
Windows Spelling | windows | Yes | Yes | locale-specific | system-managed | not-required | pass | not-run | —
<!-- target-capabilities:end -->

## Sublime Text

Target id: `sublime`.

### How Spell Sync stores words

Spell Sync does **not** edit your main Sublime settings file
(`Packages/User/Preferences.sublime-settings`).

It writes a small package preferences file:

`Packages/SpellSync/Preferences.sublime-settings`

that contains only an `added_words` list (your personal vocabulary for Sublime’s
spell checker). Theme, font, `spell_check`, base `dictionary`, key bindings, and other
editor settings stay under your control in User preferences (or other packages).

On **Update my apps**, that SpellSync file is replaced as a whole with the current word
list. Do not store unrelated settings there — the next Update overwrites the file.

### How Sublime applies the list

Sublime merges settings from several layers. **User preferences win** over package
preferences. If `Packages/User/Preferences.sublime-settings` also defines a non-empty
`added_words` array, Sublime uses that User list for spelling and **ignores** the
SpellSync package list for vocabulary.

That is why Update can report the Sublime target as in sync while the editor still
looks like an older dictionary: Spell Sync updated its package file, but User
`added_words` is what the spell checker actually uses.

### Recommendations

1. Keep personal vocabulary in your Spell Sync word list (`wordlist.txt`), not as a
   long-lived `added_words` block in User Preferences.
2. If you already have `added_words` in User Preferences:
   - Copy any words you still need into `wordlist.txt` by hand (or another editor).
     **Collect my words does not read User Preferences** — it only reads the SpellSync
     package file and other enabled app dictionaries.
   - Remove the `added_words` key from User Preferences so the SpellSync package layer
     can take effect.
   - Run **Update my apps**, then restart Sublime Text.
3. Leave `spell_check` and the base `.dic` dictionary path in User Preferences if you
   use them — those are editor policy, not the personal word list Spell Sync manages.
4. Run **Health** / `spell-sync doctor` (or Status) after setup: if User Preferences still
   override the package, Spell Sync warns instead of silently looking “OK”.
5. Prefer adding and removing words through Spell Sync (or the word list) rather than
   Sublime’s “Add to dictionary” when the `sublime` target is enabled. Words added inside
   Sublime usually land in User Preferences and can shadow the SpellSync package again.

### What Spell Sync never does for Sublime

- It does not rewrite User Preferences.
- It does not change Sublime’s built-in or third-party `.dic` files.
- It does not manage themes, packages, or keymaps.

## Platform validation status

All entries currently have `manual_validation: not-run` unless explicitly updated with real
evidence (application version and test date). Synthetic CI tests provide `automated_validation:
pass` only.

## Known limitations

- Windows locale custom dictionaries (`win_spelling`) apply language-specific subset filtering.
- Chrome, Edge, Firefox, and Obsidian Push may skip dictionaries while the application is running.
- macOS and Windows system spelling targets are platform-specific and not available on all OSes.
- Real spell-checker behavior beyond custom dictionary writes is not guaranteed.
- Sublime Text: User Preferences `added_words` overrides the SpellSync package layer — see
  [Sublime Text](#sublime-text).
- Real-application manual validation is recorded in `docs/technical/target-validation.json`
  and may be `not-run` even when automated synthetic tests pass.

## How to contribute a manual test result

1. Add a row to `docs/technical/target-validation.json` with `application_version`,
   `tested_on`, and repository-relative `evidence` when possible.
2. Prefer a throwaway app profile; do not mutate someone else's primary dictionaries
   without permission.
3. Regenerate the table: `python3 scripts/check_target_capabilities.py --write`.
4. Run the repository CI checks (or open a PR and rely on GitHub Actions).

Do not mark manual pass without a real test date and application version.
