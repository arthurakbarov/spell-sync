# Supported Apps

Spell Sync works with **custom dictionaries** in supported applications. It never reads or
changes **built-in** dictionaries shipped with an app.

## Quick answer: will this work with my app?

If the app lets you add personal words to a custom dictionary, Spell Sync may support it when
it appears in **Targets** after setup. Run **Check my apps** to see what was found on your
computer.

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
- Whether the app should be closed before Update (Push)

Detailed platform matrix and validation status: [Supported targets](SUPPORTED_TARGETS.md).

Technical support matrix (maintainers): [technical/TARGET_SUPPORT_MATRIX.md](technical/TARGET_SUPPORT_MATRIX.md).

## First-time tip

If nothing is found, open the app once and add **one custom word**, then run **Check my apps**
again.
