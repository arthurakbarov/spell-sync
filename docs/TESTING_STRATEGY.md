# Efficient staged testing

Canonical guide for selecting validation during spell-sync development. Full repository
CI remains mandatory once on a stable final tree; this document defines how to reach that
gate without redundant work.

## Principle

During development:

```text
smallest failing test
→ affected module tests
→ affected risk cluster
→ one final full CI
```

Do not loop:

```text
full CI → tiny edit → full CI → format fix → full CI
```

## Validation levels

### Level 0 — reproduction

Use when a specific defect is known.

```bash
python3 -m pytest tests/test_runtime_architecture.py::test_name -q
```

Goal: minimal feedback in seconds. Do not run neighboring modules unless needed to
reproduce.

### Level 1 — changed-module validation

After Level 0 passes, run tests mapped to touched production modules once.

```bash
python3 scripts/test_plan.py --explain
python3 scripts/run_focused_tests.py
```

### Level 2 — risk-cluster validation

When Level 1 is green, run the deduplicated cluster plan once. Clusters are defined in
`tests/test-impact.toml`:

| Cluster | Typical scope |
|---------|---------------|
| `runtime` | Resolver, mutation scope, runtime settings |
| `configuration` | Config, settings, project setup |
| `pull` | Pull safety and flow |
| `push` | Push writers, app guards |
| `transaction` | Journal, lock, atomic writes |
| `recovery` | Recovery commands and TUI safety |
| `tui` | Textual screens and mutation routing |
| `cli-json` | CLI commands and JSON contracts |
| `packaging` | Wheel metadata and installed workflow |
| `agent-workflow` | Cursor rules, skills, validators |
| `documentation` | Docs style and contract only |

```bash
python3 scripts/run_focused_tests.py --cluster runtime
```

### Level 3 — final repository CI

```bash
scripts/ci.sh
```

Run once when implementation, focused tests, and static corrections are complete and a
green result is expected. Diagnostic partial runs (`--only`, `--from`) do not count as
final evidence.

## Time budget guidance

| Level | Typical target |
|-------|----------------|
| Level 0 | seconds |
| Level 1 | under ~30 seconds where practical |
| Level 2 | under a few minutes |
| Level 3 | full repository time |

If Level 1 routinely exceeds a few minutes, reduce fixture overhead (session-scoped
immutable setup, smaller synthetic repos) rather than skipping safety coverage.

## Planner and runner

| Tool | Purpose |
|------|---------|
| `scripts/test_plan.py` | Select targets from git changes or explicit files |
| `scripts/run_focused_tests.py` | Execute plan with ledger deduplication |
| `tests/test-impact.toml` | Machine-readable production → test mapping |
| `.artifacts/test-runs/current.json` | Successful focused-run evidence (gitignored) |

Examples:

```bash
python3 scripts/test_plan.py
python3 scripts/test_plan.py --files spell_sync/push_prepared.py --format json
python3 scripts/run_focused_tests.py --force
```

## Ledger and deduplication

A successful focused command is recorded with a run key derived from:

- repository `HEAD`
- working-tree digest
- command argv
- selected targets and clusters
- `pyproject.toml` and `tests/test-impact.toml` digests
- Python major/minor

Identical successful runs on an unchanged tree are skipped:

```text
TEST_RUN_RESULT=skipped
TEST_RUN_REASON=already-passed-for-current-state
```

Evidence invalidates when targets, mapped production files, shared fixtures, test
configuration, Python version, or command options change.

## Docs-only changes

Documentation edits select validators only (docs style, docs contract, agent config when
agent docs change). Product pytest suites are not run during the focused loop.

## Safety-critical changes

Changes under Pull, Push, transaction, journal, lock, or Recovery paths always include the
matching safety cluster. The planner cannot omit these clusters.

## Final CI evidence

Only a successful full run with:

```json
{"mode": "full", "finalEvidence": true}
```

and matching current tree digest counts as final CI evidence. Partial diagnostic runs are
for fixing a single failed gate between full runs.

## Baseline CI reuse

When the working tree is clean and `.artifacts/ci/ci-summary.json` shows `mode=full`,
`result=success`, and matching tree digest for current `HEAD`, do not rerun baseline full
CI before starting a task. Use lightweight validators and phase-specific focused tests
instead.

Rerun baseline full CI only for unknown repository health, release operations, explicit
owner request, recent toolchain changes, or stale or failed evidence.

## Prohibited shortcuts

Do not, for speed:

- remove assertions or lower coverage thresholds
- permanently skip safety suites after mutation changes
- use `pytest --lf` or `pytest -x` as final cluster evidence
- treat partial CI as final validation
- rerun identical successful commands on an unchanged tree
- run packaging or wheel smoke during unrelated focused loops

## Developer report section

Modifying tasks should include a **Test selection** section documenting changed scope,
commands run, skipped duplicates, and full CI count (expected: 1).

See `docs/AGENT_DEVELOPMENT.md` and `.cursor/skills/select-and-run-tests/SKILL.md`.
