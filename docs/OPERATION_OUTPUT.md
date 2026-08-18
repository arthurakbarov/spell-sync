# What you see while Spell Sync runs

Human-mode CLI commands (and long waits in the TUI) follow a simple pattern so you
always know what is happening.

## Pattern

1. **Intro** — a short title and what Spell Sync is about to do.
2. **Expected duration** — if the step usually takes **5 seconds or more**, one line such as
   `Usually takes about ...`.
3. **Progress** — indented stage lines while work runs.
4. **Still working** — if nothing new has printed for a while, a heartbeat line so the
   terminal does not look stuck.
5. **Outcome** — one clear result line (`done`, warning, error, or abort), then any counts
   or next steps.

## Exceptions

- **`--json`** — machine output only; no human progress lines.
- **`spell-sync version`** — prints the version string only.
- **`spell-sync ui`** — opens the TUI; waits inside the UI use the same duration hints.

## Tips

- Rebuild a preview after you change apps or files — do not confirm an old plan.
- Letter shortcuts in the TUI and `y`/`n` confirmations follow the physical key, so they keep working if the keyboard layout is not QWERTY.
- For privacy-safe diagnostics to share when asking for help, use `spell-sync support-report`.
