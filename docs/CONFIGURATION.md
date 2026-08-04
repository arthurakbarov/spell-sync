# Configuration

`spell-sync.toml` lives beside `wordlist.txt` (project config) or at
`~/.config/spell-sync/spell-sync.toml` (user defaults). Project config wins when both exist.

If you keep the personal folder in a synced cloud directory or a Git remote, target
toggles in `spell-sync.toml` travel with the folder across machines. Adjust per machine
under **Dictionary targets** when an app is missing on that computer.

Copy from [`spell_sync/bundled/spell-sync.toml.example`](../spell_sync/bundled/spell-sync.toml.example)
or run `spell-sync init`.

Unknown sections or keys produce a **config-check** error and block mutating commands.

## `[dictionaries]`

Toggle which **application custom dictionary** categories participate in Pull and Push (all
default `true`). Enabling a target means its custom dictionary file is read during Pull and
written during Push — Spell Sync does **not** control the application's entire spell checker
or its built-in dictionaries.

During Push, most targets receive the full canonical wordlist. Some platform-specific
targets apply language- or format-specific filtering (for example Windows English custom
spelling files receive applicable Latin-script words). Configuration does not control
built-in dictionaries.

| Key | Custom dictionary targets |
|-----|---------------------------|
| `editors` | VS Code / Cursor family (`spell-sync-words.txt`) |
| `chrome`, `edge`, `brave`, `vivaldi` | Chromium custom dictionaries |
| `firefox` | `persdict.dat` profiles |
| `neovim` | `.add` spell files |
| `jetbrains` | IDE custom dictionaries |
| `hunspell` | Hunspell `.dic` user files |
| `obsidian` | Obsidian custom dictionary |
| `libreoffice` | LibreOffice user dictionary |
| `macos_spelling` | macOS AppleSpell / classic custom words (`macos`, `macos-*`); default `true`; only meaningful on macOS. Toggle in TUI **Dictionary targets** like other families. |
| `win_spelling` | Windows locale custom spelling files (`win-en`, `win-en-gb`, `win-ru`); default `true`; only meaningful on Windows. Toggle in TUI **Dictionary targets** like other families. |

Platform-specific keys default to `true` but are ignored on other operating systems.

spell-sync **never creates** custom dictionary files except via push when the target format
allows it; many targets must exist first (see `spell-sync doctor --targets`).

## `[push]`

| Key | Default | Purpose |
|-----|---------|---------|
| `guard_wordlist_max` | `10` | Abort push when wordlist has ≤ this many words but local dicts are much larger |
| `guard_local_min` | `20` | Minimum local dictionary size that triggers the tiny-wordlist guard |
| `strict` | `false` | Abort push when any dictionary would be skipped |
| `max_removals_without_confirm` | `50` | Prompt before push removes more than this many words per dictionary |

## `[io]`

| Key | Default | Purpose |
|-----|---------|---------|
| `backup_keep` | `3` | Rotating `.bak` files before overwrite (`0` disables) |

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
