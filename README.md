# spell-sync

**One canonical wordlist for all your spell-check custom dictionaries.**

*Optionally keep it in Git.*

[![CI](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml/badge.svg)](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/arthurakbarov/spell-sync)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Keep one `wordlist.txt` as the source of truth for **personal spelling exceptions** across
**application custom dictionaries** on **OS**, **browsers**, **editors and IDEs**, and
**Hunspell**. Use **Pull** to merge new words from custom dictionaries into the wordlist, and
**Push** to write applicable personal words from the wordlist to configured custom dictionaries. Version control is
optional — Spell Sync works with a local wordlist directory just as well as a Git-tracked
project.

## What the canonical wordlist contains

The canonical wordlist holds **personal spelling exceptions**: names, technical terms,
abbreviations, project-specific words, and other words you want enabled applications to
recognize.

It is **not** a complete language dictionary and **not** a copy of application built-in
dictionaries. Spell Sync reads and writes **application custom dictionaries** only. Built-in
dictionaries shipped with applications are never inspected.

Pull builds a union of personal words already in the wordlist plus words found in enabled
custom dictionaries. Push writes applicable personal words from the canonical wordlist to
those custom dictionaries. Most custom dictionaries receive the full canonical wordlist;
some platform-specific targets receive a language-specific subset (for example Windows
English targets receive applicable Latin-script words; Windows Russian targets receive
applicable Cyrillic and non-Latin words). A word may already be recognized by an
application's built-in dictionary; storing it in a custom dictionary anyway is **expected,
harmless, and safe** — Spell Sync does not try to remove that redundancy because it
cannot reproduce each application's built-in spell checker.

**Example:** A project name is already recognized by one browser but marked misspelled in
another. Keep the name in the canonical wordlist. Spell Sync may also write it to the first
browser's custom dictionary. That extra copy keeps your personal wordlist consistent across
enabled applications.

To make a personal word consistently available across enabled applications, keep it in the
canonical wordlist.

## What Spell Sync does

### Canonical wordlist

Spell Sync treats one file — usually `wordlist.txt` in your project directory — as the canonical
list of **personal spelling exceptions**. All enabled **custom dictionary** targets sync against
that file. You choose the path during setup or with `-C/--wordlist`.

### Pull (custom dictionaries → wordlist)

**Pull** reads enabled **application custom dictionaries** and merges new personal words into
the canonical wordlist (union). It never removes words from the wordlist and never reads
built-in application dictionaries. Use Pull after adding words in an app or browser custom
dictionary.

### Push (wordlist → custom dictionaries)

**Push** writes applicable personal words from the canonical wordlist to each enabled
**custom dictionary** target. Most targets receive the full canonical wordlist; some
platform-specific targets apply language- or format-specific filtering. Words present in a
custom dictionary but absent from the applicable wordlist subset may be removed — Push is
how you delete a word everywhere that target supports. Some words may remain redundantly in
a custom dictionary when an app already recognizes them by default; that is intentional and
keeps your personal wordlist consistent. Always preview first.

### Review and update (TUI)

The terminal UI offers a guided **Review and update** flow: review Pull additions, optionally Pull,
then build a fresh Push preview and optionally Push. Each step still requires explicit confirmation;
nothing runs silently.

### Targets

After setup, open **Targets** in the dashboard to enable or disable dictionary targets. Changes
update `spell-sync.toml` only — they do not modify wordlists, application dictionaries, or journals.

### Safety previews

Every mutating operation starts from an immutable preview plan. Confirmation binds to that exact plan;
if the wordlist or a target file changes before execution, Spell Sync stops safely instead of
re-planning silently. Push with removals requires typing **`PUSH`**.

### Recovery

If Push is interrupted, a transaction journal and snapshots remain. Run **Review recovery** (TUI) or
`spell-sync recover` (CLI) to restore consistency. Successful recovery removes journal artifacts;
external changes to conflicted files are not overwritten without warning.

### History privacy

Operation history stores counts, outcomes, and opaque identifiers — never your words. Technical logs
are redacted and bounded. See [Architecture](docs/ARCHITECTURE.md) for details.

## Install

### From GitHub

```bash
uv tool install \
  git+https://github.com/arthurakbarov/spell-sync

uv tool update-shell   # only if the uv tools directory is not already on PATH
spell-sync
```

For release-candidate testing before a GitHub release, install from a wheel in `dist/` — see
[Manual testing](docs/MANUAL_TESTING.md).

### From a clone

```bash
git clone https://github.com/arthurakbarov/spell-sync
cd spell-sync
uv tool install .
spell-sync
```

### Development

```bash
git clone https://github.com/arthurakbarov/spell-sync
cd spell-sync
uv sync
uv run spell-sync
```

Editable install for local CLI testing:

```bash
uv tool install --editable .
```

Requires **Python 3.11+**. Python **3.11** and **3.12** are currently tested.

## Quick start

Run `spell-sync` in an empty directory (or use `spell-sync init` for a non-interactive bootstrap).

| Situation | Command |
|-----------|---------|
| Added a word in an app | `spell-sync pull` then commit `wordlist.txt` if you use Git |
| New machine / after `git pull` | `spell-sync push` |
| Delete a word everywhere | Remove from wordlist → `spell-sync push` (not pull) |
| Preview changes | `spell-sync status` or `spell-sync plan` |
| Preview removals | `spell-sync plan --removals` |
| Crash / interrupted push | `spell-sync recover` |
| Terminal UI | `spell-sync` (TTY) or `spell-sync ui` |

## CLI

| Command | Purpose |
|---------|---------|
| `init` | Create starter files from bundled examples |
| `pull` | Pull: merge dictionary words into `wordlist.txt` (union) |
| `push` | Push: write wordlist to all configured dictionaries |
| `status` | Show wordlist vs dictionary diffs |
| `plan` | Preview push without writing (`--removals` lists words push would remove) |
| `doctor` | Check paths, permissions, drift (`--targets` lists dictionary paths) |
| `recover` | Restore from unfinished push journal |
| `config-check` | Validate `spell-sync.toml` |
| `lint` | Check wordlist quality |
| `ui` | Launch the terminal UI |
| `version` | Print installed package version |

Common flags: `-C/--wordlist PATH`, `--json`, `push -n/--dry-run`, `push -y/--yes`,
`push --strict`, `push --review-removals`, `recover --discard-corrupt-journal`.

Run `spell-sync --help` for the full list.

With no subcommand on a TTY, `spell-sync` opens the dashboard when a project is ready, or the
Setup wizard when no project exists. Without a TTY, it prints usage and exits with code 2.

The supported public interface is the spell-sync CLI. Python modules are internal implementation
details.

## Documentation

| Document | Contents |
|----------|----------|
| [Configuration](docs/CONFIGURATION.md) | `spell-sync.toml` reference |
| [Recovery](docs/RECOVERY.md) | Transaction journal and `recover` |
| [Architecture](docs/ARCHITECTURE.md) | Internal design and safety model |
| [TUI implementation](docs/TUI_IMPLEMENTATION.md) | Terminal UI screen map and invariants |
| [Development](docs/DEVELOPMENT.md) | Hacking, tests, CI |
| [Manual testing](docs/MANUAL_TESTING.md) | Release checklist for human testers |
| [Contributing](docs/CONTRIBUTING.md) | Pull requests |

## Safety (summary)

- Mutating commands take a project lock (`.spell-sync.lock`).
- Push uses atomic writes, pre-write hashes, and a transaction journal (schema v2).
- On crash, run `spell-sync recover` — successful recovery removes the journal and snapshots.
- Corrupt journals fail closed; use `recover --discard-corrupt-journal` only deliberately.
- Invalid `spell-sync.toml` blocks mutating commands.
- Operation history stores counts and outcomes, not your words.

Details: [Recovery](docs/RECOVERY.md) · [Architecture](docs/ARCHITECTURE.md).

## License

[Unlicense](LICENSE) — public domain.
