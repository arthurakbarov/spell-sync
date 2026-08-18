# Troubleshooting

Symptom-based guidance for Spell Sync. For application coverage see
[Supported apps](SUPPORTED_APPS.md). Recovery details: [Recovery](RECOVERY.md).

## Contents

- [Chrome does not recognize updated words](#chrome-does-not-recognize-updated-words)
- [Sublime Text still shows an old dictionary](#sublime-text-still-shows-an-old-dictionary)
- [Firefox profile was not detected](#firefox-profile-was-not-detected)
- [Update my apps is blocked because an application is running](#update-my-apps-is-blocked-because-an-application-is-running)
- [Configuration is invalid or rejected](#configuration-is-invalid-or-rejected)
- [Configuration changed after preview](#configuration-changed-after-preview)
- [An application was skipped safely](#an-application-was-skipped-safely)
- [An application dictionary is corrupt or unreadable](#an-application-dictionary-is-corrupt-or-unreadable)
- [The personal word list is missing or unreadable](#the-personal-word-list-is-missing-or-unreadable)
- [Recovery is required](#recovery-is-required)
- [I updated my apps and want to undo it](#i-updated-my-apps-and-want-to-undo-it)
- [Words returned after Update my apps](#words-returned-after-update-my-apps)
- [An application already recognizes a word by default](#an-application-already-recognizes-a-word-by-default)
- [The support report could not be exported](#the-support-report-could-not-be-exported)
- [Spell Sync was installed but the command is not found](#spell-sync-was-installed-but-the-command-is-not-found)
- [bad interpreter when running spell-sync](#bad-interpreter-when-running-spell-sync)
- [TUI does not start in the current terminal](#tui-does-not-start-in-the-current-terminal)
- [I want to preview differences before Update my apps](#i-want-to-preview-differences-before-update-my-apps)
- [Word list quality warnings](#word-list-quality-warnings)


## Chrome does not recognize updated words

### What happened
Update my apps reported success or partial success, but Chrome still marks a word as misspelled.

### Why Spell Sync stopped or skipped
Chrome may have been running (Update my apps skips running Chromium apps), the word may be outside
the applicable subset, or Chrome may need a restart to reload its custom dictionary.

### What was changed
If Update my apps completed, applicable words were written to Chrome's custom dictionary file.

### What was not changed
Built-in Chrome dictionaries, other browser profiles you did not enable, and your personal
word list unless you also ran Collect my words.

### What to do next
Close Chrome completely, rebuild the Update preview, confirm, and run Update my apps again. Verify the app
is enabled and detected under **Applications**. Check whether the word belongs in your personal
word list.

### How to export a safe support report
Run `spell-sync support-report` or use **Health → Export support report** in the TUI.

## Sublime Text still shows an old dictionary

### What happened
Update my apps or Status reports the Sublime dictionary as up to date, but Sublime’s spell
checker still underlines words that are already in your word list (or still accepts words
you removed).

### Why Spell Sync stopped or skipped
Spell Sync writes vocabulary only to `Packages/SpellSync/Preferences.sublime-settings`.
If `Packages/User/Preferences.sublime-settings` also contains a non-empty `added_words`
list, Sublime’s settings merge prefers the User list, so the SpellSync package file is
ignored for spelling. Status can still look healthy because it compares the word list to
the SpellSync package file.

### What was changed
If Update completed, the SpellSync package preferences file was rewritten from your word
list. User Preferences were not modified.

### What was not changed
User Preferences (including any `added_words` there), themes, keymaps, and Sublime’s base
`.dic` dictionary path.

### What to do next
1. Open User Preferences and check for an `added_words` array.
2. Copy any words you still need into your Spell Sync word list by hand.
   Collect my words does **not** read User Preferences.
3. Remove `added_words` from User Preferences (keep `spell_check` / `dictionary` if you
   use them).
4. Run Update my apps again, restart Sublime, and re-check spelling.
5. Run **Health** / `spell-sync doctor` — Spell Sync warns when User Preferences still
   override the package.

Details: [Supported apps → Sublime Text](SUPPORTED_APPS.md#sublime-text).

### How to export a safe support report
Run `spell-sync support-report`.

## Firefox profile was not detected

### What happened
Firefox does not appear as a detected application.

### Why Spell Sync stopped or skipped
Spell Sync only discovers Firefox profiles that contain a readable custom dictionary path.
Unsupported or unreadable profiles are listed as unavailable, not force-enabled.

### What was changed
Nothing automatically.

### What was not changed
Firefox profiles, your word list, or Recovery state.

### What to do next
Confirm Firefox has been launched at least once, refresh detection under **Applications**,
and check file permissions. Disable the app in config if you do not use Firefox on this
machine.

### How to export a safe support report
Run `spell-sync support-report`.

## Update my apps is blocked because an application is running

### What happened
Update preview or execution skipped Chrome, Edge, Firefox, or Obsidian while the app was open.

### Why Spell Sync stopped or skipped
These apps use a running-application block to avoid writing a dictionary file the app may
have open.

### What was changed
Nothing for the skipped app.

### What was not changed
Other apps that were not blocked, your word list, and Recovery state.

### What to do next
Close the application named in the notice, rebuild the preview, and confirm Update my apps again.

### How to export a safe support report
Run `spell-sync support-report`.

## Configuration is invalid or rejected

### What happened
Mutating commands refuse to run, or doctor reports an invalid project configuration.

### Why Spell Sync stopped or skipped
`spell-sync.toml` must validate before Collect, Update, or Recovery writes. A bad path, unknown
app, or schema error fails closed.

### What was changed
Nothing.

### What was not changed
Wordlist and application custom dictionaries.

### What to do next
Run `spell-sync config-check` and fix the reported fields (`spell-sync doctor` covers
broader health, not only TOML). Then rebuild any preview before confirming writes.

### How to export a safe support report
Run `spell-sync support-report` and include `spell-sync version` output.

## Configuration changed after preview

### What happened
Collect or Update stopped with a stale preview or fingerprint mismatch notice.

### Why Spell Sync stopped or skipped
Confirmation binds to the exact prepared plan. If the word list, config, or dictionary file changed
after preview creation, execution is refused.

### What was changed
Nothing.

### What was not changed
The preview remains invalid until rebuilt; no partial write from the stale plan.

### What to do next
Rebuild the preview from the dashboard or guided review flow and confirm again. If the config
file itself looks wrong, run `spell-sync config-check` first.

### How to export a safe support report
Run `spell-sync support-report` and include `spell-sync version` output.

## An application was skipped safely

### What happened
Collect or Update completed with warnings and one or more apps marked skipped.

### Why Spell Sync stopped or skipped
Common reasons: unreadable dictionary, corrupt format, unsupported platform, or running
application policy.

### What was changed
Other ready apps may still have been updated.

### What was not changed
Skipped apps' dictionary files and built-in dictionaries.

### What to do next
Open **Applications → Details** for the affected app, follow the suggested action, refresh
detection, and rebuild the preview.

### How to export a safe support report
Run `spell-sync support-report`.

## An application dictionary is corrupt or unreadable

### What happened
Doctor, dashboard, or operation report flags an application dictionary as corrupt or unreadable.

### Why Spell Sync stopped or skipped
Spell Sync fails closed rather than overwriting or guessing at an unreadable custom dictionary.

### What was changed
Nothing for that app.

### What was not changed
Built-in dictionaries and unrelated apps.

### What to do next
Check permissions and file format, repair or restore the custom dictionary from backup, or
disable the app under **Applications** until it is healthy.

### How to export a safe support report
Run `spell-sync support-report`.

## The personal word list is missing or unreadable

### What happened
Status, Update, Health, or `init` reports that the personal word list is missing or cannot be
read. The count is not shown as zero words. A support report shows the count as unknown.

### Why Spell Sync stopped or skipped
A missing file is not an empty list. An unreadable file is not a ready project. `init` will
not create `spell-sync.toml` beside a word list it cannot read. Collect may still create a
missing list from app dictionaries.

### What was changed
Nothing. Writes stay blocked until the file is present and readable (except Collect creating
a missing list).

### What was not changed
Application custom dictionaries and Recovery state.

### What to do next
If the file is missing, run `spell-sync init` or finish **Start here**. If it exists but
cannot be read, fix permissions or restore `wordlist.txt`, then run `spell-sync doctor`.
If lint says the allow-list is unreadable, fix `lint-whitelist.txt` in the same folder.

### How to export a safe support report
Run `spell-sync support-report`.

## Recovery is required

### What happened
Dashboard or a write operation reports pending Recovery.

### Why Spell Sync stopped or skipped
An unfinished Update journal must be resolved before new writes proceed.

### What was changed
Journal and snapshots from the interrupted transaction remain until Recovery finishes.

### What was not changed
External manual edits to conflicted files are not silently overwritten.

### What to do next
Open **Finish interrupted update** in the TUI or run `spell-sync recover`. See [Recovery](RECOVERY.md).

### How to export a safe support report
Run `spell-sync support-report`.

## I updated my apps and want to undo it

### What happened
You completed Update my apps and want the previous custom-dictionary contents back.

### Why Spell Sync stopped or skipped
Spell Sync has no `rollback` command. Recovery only finishes an **interrupted** Update journal;
it does not reverse a successful Update.

### What was changed
Apps that finished successfully already have the new dictionary contents.

### What was not changed
Apps that were skipped or failed keep their previous files. Rotating `.bak` files next to
dictionaries (when the dictionary writer creates them) are not automatically restored.

### What to do next
1. Prefer restoring from the application's own backup or from your word list Git history if you
   track the personal word list.
2. If a `.bak` file exists beside an application dictionary, restore it only when you understand that
   file's format — see [Recovery](RECOVERY.md) for backup policy.
3. Re-run **Review and update** after fixing the word list if you only need a corrected Update.

### How to export a safe support report
Run `spell-sync support-report`.

## Words returned after Update my apps

### What happened
A word you removed from the word list still appears in an application.

### Why Spell Sync stopped or skipped
Collect my words only adds words. It never removes them. Removal requires Update my apps with a preview that lists removals.
Some apps may have been skipped, or the word may still exist in another enabled app
that Collect merges back.

### What was changed
Update writes only apps that completed successfully.

### What was not changed
Built-in dictionary recognition and skipped apps.

### What to do next
Confirm the word is absent from the personal word list, run `spell-sync plan --removals`,
then Update my apps with confirmation. Check **Applications → Details** for skipped apps.

### How to export a safe support report
Run `spell-sync support-report`.

## An application already recognizes a word by default

### What happened
Update wrote a word that the application already accepts via its built-in dictionary.

### Why Spell Sync stopped or skipped
Spell Sync does not inspect built-in dictionaries and does not remove harmless redundancy.

### What was changed
The word may now also exist in the custom dictionary.

### What was not changed
Built-in dictionaries.

### What to do next
No action required unless you want a smaller custom dictionary for manual inspection. Keeping
the word in the personal word list preserves cross-application consistency.

### How to export a safe support report
Not usually necessary for this harmless case.

## The support report could not be exported

### What happened
`spell-sync support-report` or the TUI export action failed.

### Why Spell Sync stopped or skipped
Common causes: output path already exists, state directory not writable, or project paths
could not be inspected safely.

### What was changed
No report file was written when export failed.

### What was not changed
Wordlists, dictionaries, and operation history.

### What to do next
Choose a new output path with `--output`, ensure the application state directory is writable,
and run `spell-sync doctor`. Retry export after fixing permissions.

### How to export a safe support report
Use `--output /path/to/new-report.json` after resolving the error above. Include
`spell-sync version` when you share the report.

## Spell Sync was installed but the command is not found

### What happened
The shell cannot find `spell-sync` after install.

### Why Spell Sync stopped or skipped
The install succeeded but the tool directory is not on `PATH`.

### What was changed
The package was installed into the Python environment or uv tool directory.

### What was not changed
Your project files.

### What to do next
Re-open the terminal, run `uv tool update-shell` if you used `uv tool install`, or invoke
`python -m spell_sync` from the same environment.

### How to export a safe support report
After the command is available, run `spell-sync support-report`.

## bad interpreter when running spell-sync

### What happened
The shell prints something like:

```text
zsh: /opt/homebrew/bin/spell-sync: bad interpreter: /opt/homebrew/opt/python@3.11/bin/python3.11: no such file or directory
```

### Why Spell Sync stopped or skipped
A console-script shim still points at a Python that was upgraded or removed (common after
`pip install -e` into Homebrew Python).

### What was changed
Nothing by Spell Sync itself — the interpreter path in the shim is stale.

### What was not changed
Your word list and project files.

### What to do next
Prefer an isolated install and remove the broken shim:

```bash
rm -f /opt/homebrew/bin/spell-sync
uv tool install --force --python 3.14 git+https://github.com/arthurakbarov/spell-sync@v1.0.0
uv tool update-shell   # once, if needed
hash -r
spell-sync version
```

Do not reinstall with `pip install -e` into Homebrew/system Python.

### How to export a safe support report
After `spell-sync version` works, run `spell-sync support-report`.

## TUI does not start in the current terminal

### What happened
`spell-sync` or `spell-sync ui` exits immediately or prints a non-interactive error.

### Why Spell Sync stopped or skipped
The TUI requires a TTY on stdin and stdout. Pipes, CI, and some IDE terminals are
non-interactive.

### What was changed
Nothing.

### What was not changed
Project data.

### What to do next
Run from a normal terminal emulator, use explicit CLI commands, or pass `--help` to inspect
available commands.

### How to export a safe support report
Use `spell-sync support-report` from the CLI when the TUI is unavailable.

## I want to preview differences before Update my apps

### What happened
You want to see what would change before writing application custom dictionaries.

### Why Spell Sync stopped or skipped
Nothing is wrong — preview is intentional. Update my apps never runs automatically from
`status` or `plan`.

### What was changed
Nothing. Preview commands are read-only.

### What was not changed
Wordlist, application dictionaries, and Recovery state.

### What to do next
Run `spell-sync status` (**Check my apps**) for a short drift summary, or
`spell-sync plan` for a detailed Update my apps preview. In the TUI, open
**Check my apps** for readiness/drift, or **Update my apps** /
**Review and update** to review the Update preview before confirming.

### How to export a safe support report
Run `spell-sync support-report` if preview output looks unexpected.

## Word list quality warnings

### What happened
You want to check the personal word list for quality issues before Collect or Update.

### Why Spell Sync stopped or skipped
Lint is advisory quality checking; it does not mutate dictionaries by itself.

### What was changed
Nothing unless you edit the word list afterward.

### What was not changed
Application custom dictionaries and Recovery state.

### What to do next
Run `spell-sync lint` and fix or accept reported warnings in your personal word list. If lint
says the allow-list is unreadable, fix `lint-whitelist.txt` before treating soft warnings as
real. Rebuild any Update preview after editing the word list.

### How to export a safe support report
Run `spell-sync support-report` after resolving path or permission issues if lint cannot read
the word list.

