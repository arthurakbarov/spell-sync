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

After Level 0 passes, run `moduleTests` mapped to touched production modules once. Level 1
is intentionally smaller than Level 2: direct module regressions and minimal integration
only.

```bash
python3 scripts/test_plan.py --explain
python3 scripts/run_focused_tests.py
```

### Level 2 — risk-cluster validation

When Level 1 is green, run the deduplicated `clusterTests` plan once. Level 2 must be a
strict superset of Level 1 for each cluster (except documented tiny clusters). Level 1
does not replace mandatory Level 2 before final CI.

Clusters are defined in `tests/test-impact.toml`:

| Cluster | Typical scope |
|---------|---------------|
| `runtime` | Resolver, mutation scope, runtime settings |
| `configuration` | Config, settings, project setup |
| `pull` | Pull safety, sync_run, dry-run, TUI pull flow |
| `push` | Push writers, app guards |
| `transaction` | Journal, lock, atomic writes, secure internal artifacts |
| `recovery` | Recovery commands, discard safety, TUI recovery |
| `tui` | Textual screens and mutation routing |
| `cli-json` | CLI commands and JSON contracts |
| `packaging` | Wheel metadata and installed workflow |
| `agent-workflow` | Cursor rules, skills, validators |
| `documentation` | Docs style and contract only |
| `diagnostics-events` | Technical events and history privacy |
| `execution-control` | Execution budgets, admission, stall contracts |
| `user-documentation` | User docs and onboarding copy validators |
| `test-selection` | Focused-test planner and impact registry |

```bash
python3 scripts/run_focused_tests.py --cluster runtime
```

### Level 3 — final repository CI

Full mode requires a clean committed working tree (`bootstrap.clean-tree`). Uncommitted
source changes fail before expensive checks. Diagnostic partial runs (`--only`, `--from`,
`--resume-failed`) may run on a dirty tree but set `finalEvidence=false`.

Final evidence requires committed clean CI-relevant state verified by
`python3 scripts/check_ci_evidence.py`.

Full CI evidence is bound to **CI-relevant inputs** (`ciInputDigest`), not merely to the Git
commit identifier. A later non-CI commit may reuse successful full CI evidence only when the
CI input digest is unchanged and current lightweight validation succeeds.

Exact Git HEAD matching remains required for release, publication, and signed artifact
workflows (`python3 scripts/check_ci_evidence.py --release`).

Before final validation, assess necessity:

```bash
python3 scripts/check_ci_necessity.py --explain
```

| Result | Action |
|--------|--------|
| `full-required` | `scripts/ci.sh` then `python3 scripts/check_ci_evidence.py` |
| `lightweight-sufficient` | `python3 scripts/run_lightweight_validation.py` then `python3 scripts/check_ci_evidence.py` |
| `no-action` | Do not rerun full CI |

```bash
scripts/ci.sh
```

## Time budget guidance

| Level | Typical target |
|-------|----------------|
| Level 0 | seconds |
| Level 1 | module: typically ≤45s expected (registry `focused-module`) |
| Level 2 | cluster: typically ≤120s expected; if plan prediction exceeds `editLoopBudgetSeconds` (120), optional scope may narrow |
| Level 3 | full CI: once per stable tip (~10 min today; improve via profiling, not by skipping) |

Keep most edit-session runs focused so mean wall time stays around 2 minutes. If Level 1
routinely exceeds the focused-module expectation, reduce fixture overhead (session-scoped
immutable setup, smaller synthetic repos) rather than skipping safety coverage. Required
safety clusters are never dropped for budget reasons.

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

Internal artifact security changes (lock, journal temp/publication, transaction root) require:

| Suite | Purpose |
|-------|---------|
| `tests/test_secure_artifacts_adversarial.py` | Mandatory R1–R7 adversarial regressions |
| `tests/test_internal_artifact_security.py` | Adversarial symlink/reparse and rollback preserve |
| `tests/test_secure_artifacts.py` | Unit coverage for `secure_artifacts` branches |
| `tests/test_transaction_safety.py` | End-to-end mutation fault matrix |

Verify victim files outside trusted root are unchanged in adversarial scenarios. Do not use real
application dictionaries.

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

## Execution time control

Registered expensive commands (focused runner, pre-final, full CI children) run through the
execution controller — not as unbounded direct subprocess calls.

Decision order before execution:

```text
CI necessity → functional evidence reuse → duplicate check → admission → immutable plan → run
```

Integrated runners (`run_focused_tests.py`, `run_pre_final_checks.py`, `ci_runner.py`) invoke
the controller automatically. Admission may skip execution when evidence is valid
(`EXECUTION_RESULT=reused`) or narrow over-budget edit-loop plans. Each run receives expected,
soft, and hard thresholds printed as `EXECUTION_*` lines.

Do not wrap CI with `tail`, `tee`, or other pipeline wrappers. Run `scripts/ci.sh` directly so
hard bounds and child timeout IDs remain authoritative.

Registry: `tests/execution-budget.toml`. Canonical detail: `docs/EXECUTION_TIME_CONTROL.md`.

## Developer report section

Modifying tasks should include a **Test selection** section documenting changed scope,
commands run, skipped duplicates, execution reuse decisions, and full CI count (expected: 1).

See `docs/AGENT_DEVELOPMENT.md` and `.cursor/skills/select-and-run-tests/SKILL.md`.
