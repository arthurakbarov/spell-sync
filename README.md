# spell-sync

**One git-tracked wordlist for all your personal spell-check dictionaries.**

[![CI](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml/badge.svg)](https://github.com/arthurakbarov/spell-sync/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/arthurakbarov/spell-sync)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Keep one canonical `wordlist.txt` and use **Pull** (applications → wordlist) and **Push**
(wordlist → applications) to stay in sync across **OS**, **browsers**, **editors and IDEs**, and
**Hunspell**.

## Install

### From GitHub (recommended after release)

Install directly from GitHub once the **0.1.0 release candidate** has been pushed to the
remote repository:

```bash
uv tool install \
  git+https://github.com/arthurakbarov/spell-sync

uv tool update-shell   # only if the uv tools directory is not already on PATH
spell-sync
```

Before that push, external testers should install from the handoff artifacts instead: the wheel
(`dist/spell_sync-0.1.0-py3-none-any.whl`) or source ZIP (`dist/spell-sync-0.1.0-source.zip`).
See [Manual testing](docs/MANUAL_TESTING.md).

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
| Added a word in an app | `spell-sync pull` then commit `wordlist.txt` |
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
| [Development](docs/DEVELOPMENT.md) | Hacking, tests, CI |
| [Manual testing](docs/MANUAL_TESTING.md) | Release candidate checklist for human testers |
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
