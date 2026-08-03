# Troubleshooting

Symptom-based guidance for Spell Sync. For target capability limits see
[Supported targets](SUPPORTED_TARGETS.md). For real-application validation workflow see
[Manual testing](MANUAL_TESTING.md) and Recovery details in [Recovery](RECOVERY.md).

## Chrome does not recognize pushed words

### What happened
Push reported success or partial success, but Chrome still marks a word as misspelled.

### Why Spell Sync stopped or skipped
Chrome may have been running (Push skips running Chromium targets), the word may be outside
the applicable subset, or Chrome may need a restart to reload its custom dictionary.

### What was changed
If Push completed, applicable words were written to Chrome's custom dictionary file.

### What was not changed
Built-in Chrome dictionaries, other browser profiles you did not enable, and your canonical
wordlist unless you also ran Pull.

### What to do next
Close Chrome completely, rebuild the Push preview, confirm, and Push again. Verify the target
is enabled and detected under **Targets**. Check whether the word belongs in your canonical
wordlist.

### How to export a safe support report
Run `spell-sync support-report` or use **Health → Export support report** in the TUI.

## Firefox profile was not detected

### What happened
Firefox does not appear as a detected target.

### Why Spell Sync stopped or skipped
Spell Sync only discovers Firefox profiles that contain a readable custom dictionary path.
Unsupported or unreadable profiles are listed as unavailable, not force-enabled.

### What was changed
Nothing automatically.

### What was not changed
Firefox profiles, wordlist, or journal state.

### What to do next
Confirm Firefox has been launched at least once, refresh target detection in **Targets**,
and check file permissions. Disable the target in config if you do not use Firefox on this
machine.

### How to export a safe support report
Run `spell-sync support-report`.

## Push is blocked because an application is running

### What happened
Push preview or execution skipped Chrome, Edge, Firefox, or Obsidian while the app was open.

### Why Spell Sync stopped or skipped
These targets use a running-application block to avoid writing a dictionary file the app may
have open.

### What was changed
Nothing for the skipped target.

### What was not changed
Other targets that were not blocked, your wordlist, and Recovery state.

### What to do next
Close the application named in the notice, rebuild the preview, and confirm Push again.

### How to export a safe support report
Run `spell-sync support-report`.

## Configuration is invalid or rejected

### What happened
Mutating commands refuse to run, or doctor reports an invalid project configuration.

### Why Spell Sync stopped or skipped
`spell-sync.toml` must validate before Pull, Push, or Recovery writes. A bad path, unknown
target, or schema error fails closed.

### What was changed
Nothing.

### What was not changed
Wordlist and application custom dictionaries.

### What to do next
Run `spell-sync config-check` (or `spell-sync doctor`) and fix the reported fields. Then rebuild
any preview before confirming writes.

### How to export a safe support report
Run `spell-sync support-report` and include `spell-sync version` output.

## Configuration changed after preview

### What happened
Pull or Push stopped with a stale preview or fingerprint mismatch notice.

### Why Spell Sync stopped or skipped
Confirmation binds to the exact prepared plan. If the wordlist, config, or target file changed
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

## A target was skipped safely

### What happened
Pull or Push completed with warnings and one or more targets marked skipped.

### Why Spell Sync stopped or skipped
Common reasons: unreadable dictionary, corrupt format, unsupported platform, or running
application policy.

### What was changed
Other ready targets may still have been updated.

### What was not changed
Skipped targets' dictionary files and built-in dictionaries.

### What to do next
Open **Targets → Details** for the affected target, follow the suggested action, refresh
detection, and rebuild the preview.

### How to export a safe support report
Run `spell-sync support-report`.

## A target is corrupt or unreadable

### What happened
Doctor, dashboard, or operation report flags a dictionary target as corrupt or unreadable.

### Why Spell Sync stopped or skipped
Spell Sync fails closed rather than overwriting or guessing at an unreadable custom dictionary.

### What was changed
Nothing for that target.

### What was not changed
Built-in dictionaries and unrelated targets.

### What to do next
Check permissions and file format, repair or restore the custom dictionary from backup, or
disable the target in **Targets** until it is healthy.

### How to export a safe support report
Run `spell-sync support-report`.

## Recovery is required

### What happened
Dashboard or a write operation reports pending Recovery.

### Why Spell Sync stopped or skipped
An unfinished Push journal must be resolved before new writes proceed.

### What was changed
Journal and snapshots from the interrupted transaction remain until Recovery finishes.

### What was not changed
External manual edits to conflicted files are not silently overwritten.

### What to do next
Open **Review recovery** in the TUI or run `spell-sync recover`. See [Recovery](RECOVERY.md).

### How to export a safe support report
Run `spell-sync support-report`.

## Words returned after Push

### What happened
A word you removed from the wordlist still appears in an application.

### Why Spell Sync stopped or skipped
Pull only adds words (union). Removal requires Push with a preview that lists removals.
Some targets may have been skipped, or the word may still exist in another enabled target
that Pull merges back.

### What was changed
Push updates only targets that completed successfully.

### What was not changed
Built-in dictionary recognition and skipped targets.

### What to do next
Confirm the word is absent from the canonical wordlist, run `spell-sync plan --removals`,
then Push with confirmation. Check **Targets → Details** for skipped targets.

### How to export a safe support report
Run `spell-sync support-report`.

## An application already recognizes a word by default

### What happened
Push wrote a word that the application already accepts via its built-in dictionary.

### Why Spell Sync stopped or skipped
Spell Sync does not inspect built-in dictionaries and does not remove harmless redundancy.

### What was changed
The word may now also exist in the custom dictionary.

### What was not changed
Built-in dictionaries.

### What to do next
No action required unless you want a smaller custom dictionary for manual inspection. Keeping
the word in the canonical wordlist preserves cross-application consistency.

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
