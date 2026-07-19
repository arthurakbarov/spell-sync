# Manual testing — Spell Sync 0.1.0

This checklist is for a human tester validating the **0.1.0 release candidate** before wider
distribution. Use synthetic dictionary targets only. Do not test against real personal
spell-check data unless you accept the risk of file changes.

## Test environment

Record before you start:

| Field | Your value |
|-------|------------|
| OS and version | |
| Terminal app | |
| Python version | |
| Installation method | wheel / source archive / git clone |
| Package version (`spell-sync version`) | expect `0.1.0` |
| Temporary test directory | e.g. `~/spell-sync-rc-test` |
| Synthetic targets used | e.g. Cursor `spell-sync-words.txt`, local text file |

Recommended: create a fresh directory and, if possible, use a temporary `HOME` or test user
account so application state does not mix with daily use.

## Installation

From the handoff artifacts in the repository root (or a copy you received):

```bash
uv tool install ./spell_sync-0.1.0-py3-none-any.whl
spell-sync version
spell-sync --help
```

Expected:

- Version prints `0.1.0`.
- Help lists commands: `status`, `pull`, `push`, `plan`, `config-check`, `lint`, `recover`,
  `init`, `doctor`, `version`, `ui`.
- Pull and Push descriptions mention direction (applications → wordlist / wordlist → applications).

## First launch

In an empty test directory:

```bash
cd ~/spell-sync-rc-test
spell-sync
```

Check:

- [ ] TUI opens (dashboard or Setup, depending on project state).
- [ ] Welcome screen is visible when no project exists.
- [ ] Pull and Push directions are understandable before any file changes.
- [ ] Keyboard navigation works (Tab, Enter, Escape).
- [ ] Mouse clicks work on buttons where shown.
- [ ] **Quit** from Welcome exits without creating project files.

Optional feedback (no launcher in 0.1.0):

> Would a desktop or Start Menu launcher improve this workflow?

## Setup

From Welcome, run the Setup wizard:

- [ ] Choose or confirm wordlist location.
- [ ] Enable and disable at least one target; Refresh updates the list.
- [ ] Preview shows files to be created and enabled targets.
- [ ] Confirm and create the project.
- [ ] Setup report lists created files.
- [ ] External application dictionaries were **not** modified during setup.
- [ ] Quit and relaunch `spell-sync` — wizard does **not** appear again.

## Status and Doctor

- [ ] **Status** shows wordlist vs dictionary diffs; headings are readable.
- [ ] **Doctor** shows paths, permissions, and actionable warnings.
- [ ] Enabled targets match `spell-sync.toml`.
- [ ] Invalid `spell-sync.toml` blocks mutating operations with a clear message (test by
  introducing a syntax error, then attempting Pull or Push).

## Pull

Use a synthetic dictionary that contains at least one word not in the wordlist.

- [ ] Pull screen states direction (applications → wordlist).
- [ ] Preview shows addition count and differs from execution screen.
- [ ] Confirmation shows number of additions.
- [ ] Execute Pull; report shows completion.
- [ ] Wordlist bytes change as expected.
- [ ] Operation history records the Pull (counts only — open **Logs**).
- [ ] Technical log contains no wordlist words or secrets (tail via **Logs → Technical log**).

## Push

Ensure wordlist and synthetic target differ (e.g. after Pull).

- [ ] Push screen states direction (wordlist → applications).
- [ ] Preview shows planned writes and any removals.
- [ ] If removals are present, typed **`PUSH`** is required.
- [ ] Execute Push; report shows completion.
- [ ] Target file updates as expected.
- [ ] Change the target file externally after preview — execution must **not** silently
  re-plan; expect a controlled conflict or stale-preview block.

## Recovery

Simulate an interrupted Push (e.g. kill the process during operation, or use a test journal if
you have a reproducer):

- [ ] Dashboard shows recovery required / blocked state.
- [ ] Recovery screen distinguishes **Recover** vs **Discard**.
- [ ] Recovery preview is readable.
- [ ] Typed **`RECOVER`** required where applicable.
- [ ] Successful recovery restores consistency and re-enables Pull/Push.
- [ ] External changes to a conflicted file are not overwritten without warning.

## Logs

- [ ] Empty history shows an empty state (fresh install).
- [ ] Filters (operation / outcome) work.
- [ ] Record details show counts and outcomes, not dictionary words.
- [ ] Privacy line visible: *Operation history stores counts and outcomes, not your words.*
- [ ] Technical log tail is bounded (not the entire file on disk).
- [ ] Clear history asks for confirmation; technical log is **not** deleted.
- [ ] Failed history write (if reproduced) appears as a secondary warning, not a crash.

## Terminal behavior

Test window sizes:

| Size | Notes |
|------|-------|
| 80×24 | minimum |
| 100×30 | comfortable |
| 120×40 | wide |

Also check:

- [ ] Resize while a screen is open — layout remains usable; primary actions reachable.
- [ ] Unicode in UI labels (if any) renders or has text fallback.
- [ ] `NO_COLOR=1` (or terminal without color) — status remains understandable without color alone.
- [ ] Long paths and messages wrap without breaking layout.
- [ ] Keyboard-only session completes Setup → Pull → Push → Quit.

## Second launch

After a successful session:

- [ ] No Setup wizard.
- [ ] Project loads from disk.
- [ ] Operation history from prior session is still present.
- [ ] No stale `.spell-sync.lock`.
- [ ] No unfinished transaction blocking dashboard (unless you left one intentionally).

## Uninstall

```bash
uv tool uninstall spell-sync
```

Application state is **not** removed automatically. Document what remains on your system:

| Platform | State directory | Technical log |
|----------|-----------------|---------------|
| macOS | `~/Library/Application Support/spell-sync/` | `~/Library/Logs/spell-sync/spell-sync.log` |
| Linux | `~/.local/state/spell-sync/` (or `$XDG_STATE_HOME/spell-sync/`) | same directory / `spell-sync.log` |
| Windows | `%LOCALAPPDATA%\spell-sync\` | `%LOCALAPPDATA%\spell-sync\logs\spell-sync.log` |

Project-level files (in your test directory) are separate: `wordlist.txt`, `spell-sync.toml`,
`.spell-sync.lock`, `.spell-sync.txn/`, push journal files. Remove manually if desired.

## Reporting

Use [`TEST_REPORT_TEMPLATE.md`](TEST_REPORT_TEMPLATE.md) to submit findings.
