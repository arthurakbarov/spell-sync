# Configuration

`spell-sync.toml` lives beside `wordlist.txt`. There is no separate user-level config file.

## Finding your word list

Spell Sync resolves the word list in this order:

1. `--wordlist PATH` on the command line
2. `wordlist.txt` / `spell-sync.toml` in the current directory (or a parent)
3. The last word list you opened or created (machine-local pointer)
4. Otherwise `./wordlist.txt` under the current directory (setup wizard)

The pointer and recent list are stored with other machine state (not in the project
folder): `active-project.json` under the platform state directory (macOS
`~/Library/Application Support/spell-sync/`, Linux `~/.local/state/spell-sync/`,
Windows `%LOCALAPPDATA%\spell-sync\`). Open existing / Change word list in the TUI
show up to five recent paths.

If you keep the personal folder in a synced cloud directory or a Git remote, target
toggles in `spell-sync.toml` travel with the folder across machines. Adjust per machine
under **Applications** when an app is missing on that computer.

Copy from [`spell_sync/bundled/spell-sync.toml.example`](../spell_sync/bundled/spell-sync.toml.example)
or run `spell-sync init`.

Unknown sections or keys produce a **config-check** error and block Collect, Update,
and other commands that change files.

## `[dictionaries]`

Toggle which **application custom dictionary** categories participate in Collect and Update (all
default `true`). Enabling an app means its custom dictionary file is read during Collect and
written during Update — Spell Sync does **not** control the application's entire spell checker
or its built-in dictionaries.

During Update, most apps receive the full personal word list. Some platform-specific
apps apply language- or format-specific filtering (for example Windows English custom
spelling files receive applicable Latin-script words). Configuration does not control
built-in dictionaries.

| Key | Custom dictionary apps |
|-----|---------------------------|
| `editors` | VS Code / Cursor family (`spell-sync-words.txt`) |
| `chrome`, `edge`, `brave`, `vivaldi` | Chromium custom dictionaries |
| `firefox` | `persdict.dat` profiles |
| `neovim` | `.add` spell files |
| `sublime` | Sublime Text — `Packages/SpellSync/Preferences.sublime-settings` only. See [Supported apps → Sublime Text](SUPPORTED_APPS.md#sublime-text). |
| `jetbrains` | IDE custom dictionaries |
| `hunspell` | Hunspell `.dic` user files |
| `obsidian` | Obsidian custom dictionary |
| `libreoffice` | LibreOffice user dictionary |
| `macos_spelling` | macOS AppleSpell / classic custom words (`macos`, `macos-*`); default `true`; only meaningful on macOS. Toggle in TUI **Applications** like other families. |
| `win_spelling` | Windows locale custom spelling files (`win-en`, `win-en-gb`, `win-ru`); default `true`; only meaningful on Windows. Toggle in TUI **Applications** like other families. |
| `excluded` | Optional array of exact dictionary names to skip while their family stays enabled (for example `["editor:vscode", "macos-applespell"]`). Omit or `[]` means every discovered dictionary in an enabled family participates. Toggle under **Applications** as child checkboxes when a family has more than one dictionary. |

Platform-specific keys default to `true` but are ignored on other operating systems.

spell-sync **never creates** custom dictionary files except via push when the app format
allows it; many application dictionaries must exist first (see `spell-sync doctor --targets`).

## `[push]`

| Key | Default | Purpose |
|-----|---------|---------|
| `guard_wordlist_max` | `10` | Abort push when wordlist has ≤ this many words but local dicts are much larger |
| `guard_local_min` | `20` | Minimum local dictionary size that triggers the tiny-wordlist guard |
| `strict` | `false` | Abort push when any dictionary would be skipped |
| `max_removals_without_confirm` | `50` | Prompt before push removes more than this many words per dictionary. The same ceiling filters "View additions" in the TUI: dictionaries receiving more additions than this are treated as full sync dumps and omitted from that list. |

## `[io]`

| Key | Default | Purpose |
|-----|---------|---------|
| `backup_keep` | `3` | Rotating `*.bak` / `*.1.bak` / `*.2.bak` before overwrite (`0` disables) |

## `[neovim]`

| Key | Default | Purpose |
|-----|---------|---------|
| `mkspell_after_push` | `false` | Run `:mkspell` after push when `nvim` is on PATH |

## Validation

```bash
spell-sync config-check
spell-sync config-check --json
```

Invalid syntax, unknown keys, or wrong types → exit **1** with diagnostics. Mutating commands
use the same validation under the operation lock.
