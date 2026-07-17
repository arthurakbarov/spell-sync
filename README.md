# spell-sync

**One git-tracked wordlist for all your personal spell-check dictionaries.**

[![CI](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml/badge.svg)](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/arthurakbarov/spell-sync)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Sync custom words across **OS**, **browsers**, **editors and IDEs**, and **Hunspell** with one
`wordlist.txt` and two core commands: **pull** (merge app words into the wordlist) and **push**
(write the wordlist to every configured dictionary).

## Quick start

```bash
git clone https://github.com/arthurakbarov/spell-sync.git
cd spell-sync
pip install -e .
spell-sync init
spell-sync push --dry-run
```

Creates `wordlist.txt`, `spell-sync.toml`, and `lint-whitelist.txt` in the current directory.

| Situation | Command |
|-----------|---------|
| Added a word in an app | `spell-sync pull` then commit `wordlist.txt` |
| New machine / after `git pull` | `spell-sync push` |
| Delete a word everywhere | Remove from wordlist → `spell-sync push` (not pull) |
| Preview changes | `spell-sync status` or `spell-sync plan` |
| Preview removals | `spell-sync plan --removals` |
| Crash / interrupted push | `spell-sync recover` |

## CLI

| Command | Purpose |
|---------|---------|
| `init` | Create starter files from bundled examples |
| `pull` | Merge dictionary words into `wordlist.txt` (union) |
| `push` | Write wordlist to all configured dictionaries |
| `status` | Show wordlist vs dictionary diffs (default when no subcommand) |
| `plan` | Preview push without writing (`--removals` lists words push would remove) |
| `doctor` | Check paths, permissions, drift (`--targets` lists dictionary paths) |
| `recover` | Restore from unfinished push journal |
| `config-check` | Validate `spell-sync.toml` |
| `lint` | Check wordlist quality |
| `version` | Print installed package version |

Common flags: `-C/--wordlist PATH`, `--json`, `push -n/--dry-run`, `push -y/--yes`,
`push --strict`, `push --review-removals`, `recover --discard-corrupt-journal`.

Run `spell-sync --help` for the full list.

The supported public interface is the spell-sync CLI. Python modules are internal implementation
details.

## Documentation

| Document | Contents |
|----------|----------|
| [Configuration](docs/CONFIGURATION.md) | `spell-sync.toml` reference |
| [Recovery](docs/RECOVERY.md) | Transaction journal and `recover` |
| [Architecture](docs/ARCHITECTURE.md) | Internal design and safety model |
| [Development](docs/DEVELOPMENT.md) | Hacking, tests, CI |
| [Contributing](docs/CONTRIBUTING.md) | Pull requests |

## Safety (summary)

- Mutating commands take a project lock (`.spell-sync.lock`).
- Push uses atomic writes, pre-write hashes, and a transaction journal (schema v2).
- On crash, run `spell-sync recover` — successful recovery removes the journal and snapshots.
- Corrupt journals fail closed; use `recover --discard-corrupt-journal` only deliberately.
- Invalid `spell-sync.toml` blocks mutating commands.

Details: [Recovery](docs/RECOVERY.md) · [Architecture](docs/ARCHITECTURE.md).

## Install

| Method | Command |
|--------|---------|
| Editable (developers) | `pip install -e .` |
| Isolated CLI | `pipx install .` or `uv tool install .` |
| Module | `python -m spell_sync` |

Requires **Python 3.11+**.

## License

[Unlicense](LICENSE) — public domain.
