# Manual testing

Human release checklist for Spell Sync. Use synthetic dictionary targets by default. Test against
real personal spell-check data only when you accept file mutation risk.

## Manual validation policy

Manual validation records belong in `docs/target-validation.json` — not in one-off readiness
reports.

| Requirement | Detail |
|-------------|--------|
| Throwaway profiles | Use dedicated browser/editor profiles when mutating real dictionaries |
| Application version | Record exact version per target when marking `manual_validation: pass` |
| Evidence | Redacted notes only — no wordlist contents or owner paths in public commits |
| Safe without mutation | `check-target-capabilities`, `doctor --targets`, Targets → Details, synthetic HOME smoke |
| Matrix default | All rows start `not-run` until owner-approved manual pass |

Follow `.cursor/skills/platform-validation/SKILL.md` in the maintainer workspace when updating
the matrix.

## Test environment

Record before you start:

| Field | Your value |
|-------|------------|
| OS and version | |
| Terminal app | |
| Python version | |
| Installation method | wheel / source archive / git clone |
| Package version (`spell-sync version`) | match `pyproject.toml` |
| Temporary test directory | e.g. `~/spell-sync-rc-test` |
| Synthetic targets used | e.g. Cursor `spell-sync-words.txt`, local text file |

Recommended: create a fresh directory and, if possible, use a temporary `HOME` or test user
account so application state does not mix with daily use.

## Installation

From the repository checkout (release artifacts live in `dist/`):

```bash
python3 -m pip install dist/spell_sync-*.whl
spell-sync version
spell-sync --help
```

Expected:

- Version matches `project.version` in `pyproject.toml`.
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
- [ ] Pull and Push directions mention **custom dictionaries** (not built-in dictionaries).
- [ ] Welcome explains personal spelling exceptions and states built-in dictionaries are not inspected.
- [ ] Wordlist setup explains what belongs in the canonical list (names, terms, abbreviations).
- [ ] Pull preview says words come from **application custom dictionaries**.
- [ ] Push preview mentions harmless redundancy when a word may already be recognized by default.
- [ ] Push preview mentions applicable personal words and target-specific filtering where relevant.
- [ ] Push preview does not claim every target receives the full unfiltered wordlist.
- [ ] Redundancy notice refers to personal wordlist consistency, not identical spell-checker behavior.
- [ ] UI does not imply Spell Sync modifies built-in application dictionaries.
- [ ] Difference between custom dictionary files and built-in spell check is clear to a new tester.
- [ ] Keyboard navigation works (Tab, Enter, Escape).
- [ ] Mouse clicks work on buttons where shown.
- [ ] **Quit** from Welcome exits without creating project files.

## Setup

From Welcome, run the Setup wizard:

- [ ] Choose or confirm wordlist location.
- [ ] Enable and disable at least one target; Refresh updates the list.
- [ ] Preview shows files to be created and enabled targets.
- [ ] Confirm and create the project.
- [ ] Setup report lists created files.
- [ ] External application dictionaries were **not** modified during setup.
- [ ] Quit and relaunch `spell-sync` — wizard does **not** appear again.

## Dashboard

After setup, on the sectioned dashboard:

- [ ] Summary shows canonical wordlist path (with `~` when under home), word count, and target
  counts (ready / needs attention / disabled / unavailable).
- [ ] **Review and update** is the primary action.
- [ ] Direct actions: **Pull new words**, **Push wordlist**.
- [ ] Manage: **Targets**. Support: **Health**, **History**.
- [ ] Status available via `s` hotkey (not a dashboard button).
- [ ] Last operation summary appears when history exists (counts only, no words).
- [ ] Blocking banner when config is invalid or wordlist unreadable.

## Targets update

From Dashboard → **Targets**:

- [ ] Target list loads with enable/disable toggles; Refresh updates discovery.
- [ ] **Select available** and **Clear selection** behave predictably.
- [ ] **Review changes** shows enabled/disabled diff before confirm.
- [ ] Confirm and execute; report shows outcome.
- [ ] `spell-sync.toml` reflects selection; wordlist and application dictionaries unchanged.
- [ ] Operation history records a Targets entry (counts only).
- [ ] Disable a target that was enabled at setup — Push no longer writes to it.
- [ ] Re-enable a previously disabled target — Push includes it again after preview.

### Target disabled after setup

- [ ] Complete setup with target A enabled.
- [ ] Targets → disable A → confirm update.
- [ ] Push preview and execution skip A; other enabled targets still update.
- [ ] Pull still reads only enabled targets.

## Review and update

From Dashboard → **Review and update**:

- [ ] Start screen explains Pull-then-Push flow; nothing runs without confirmation.
- [ ] Pull review shows additions count and direction (applications → wordlist).
- [ ] **Pull words** opens confirm screen; cancel returns without changes.
- [ ] After Pull, **Pull complete** screen appears when wordlist changed.
- [ ] Fresh Push preview loads (never reuses pre-Pull preview).
- [ ] **Push changes** requires confirm (and typed **`PUSH`** if removals).
- [ ] Session report summarizes what ran; Dashboard reachable from report.
- [ ] Failed or recovery-required Pull/Push ends session with clear note.

### Pull skip

- [ ] Start review with synthetic words only in targets (not yet in wordlist).
- [ ] On Pull review, choose **Skip Pull**.
- [ ] Fresh Push preview still builds.
- [ ] Wordlist bytes unchanged; Push preview reflects current wordlist vs targets.

### Push skip

- [ ] Complete Pull in review (or skip Pull with divergent targets).
- [ ] On Push review, choose **Finish without Push**.
- [ ] Session report shows Pull outcome only; target files unchanged by Push.
- [ ] History records Pull if executed; no Push record for skipped Push.

## Status and Health

- [ ] **Status** (`s`) shows wordlist vs dictionary diffs; headings are readable.
- [ ] **Health** shows paths, permissions, and actionable warnings (formerly Doctor).
- [ ] Enabled targets match `spell-sync.toml`.
- [ ] Invalid `spell-sync.toml` blocks mutating operations with a clear message (test by
  introducing a syntax error, then attempting Pull or Push).

## Pull (direct)

Use a synthetic dictionary that contains at least one word not in the wordlist.

- [ ] Pull screen states direction (applications → wordlist).
- [ ] Preview shows addition count and differs from execution screen.
- [ ] Confirmation shows number of additions.
- [ ] Execute Pull; report shows completion.
- [ ] Wordlist bytes change as expected.
- [ ] Operation history records the Pull (counts only — open **History**).
- [ ] Technical log contains no wordlist words or secrets (tail via **History → Technical log**).

## Push (direct)

Ensure wordlist and synthetic target differ (e.g. after Pull).

- [ ] Push screen states direction (wordlist → applications).
- [ ] Preview shows planned writes and any removals.
- [ ] If removals are present, typed **`PUSH`** is required.
- [ ] Execute Push; report shows completion.
- [ ] Target file updates as expected.
- [ ] Change the target file externally after preview — execution must **not** silently
  re-plan; expect a controlled conflict or stale-preview block.

## Planned vs actual (reports)

After Pull or Push with at least one skipped source or target:

- [ ] Report shows **Planned** and **Actual** sections (or equivalent per-target rows).
- [ ] Skipped targets/sources have human-readable reason (not raw paths or words).
- [ ] Updated vs skipped counts match what you observed on disk.

## Changed config race

- [ ] Open Push preview (direct or via review).
- [ ] Edit `spell-sync.toml` externally (e.g. disable a target) before confirming execute.
- [ ] Execution stops safely with stale-plan or fingerprint message — no silent re-plan.
- [ ] Repeat for Targets update: change selection in UI, edit config on disk before confirm.

## Recovery

Simulate an interrupted Push (e.g. kill the process during operation, or use a test journal if
you have a reproducer):

- [ ] Dashboard shows recovery required / blocked state.
- [ ] **Review recovery** is primary; Pull/Push/Review disabled.
- [ ] Recovery screen distinguishes **Recover** vs **Discard**.
- [ ] Recovery preview is readable.
- [ ] Typed **`RECOVER`** required where applicable.
- [ ] Successful recovery restores consistency and re-enables Pull/Push/Review.
- [ ] External changes to a conflicted file are not overwritten without warning.

## History

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
- [ ] Keyboard-only session completes Setup → Review and update (or Pull → Push) → Quit.

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
