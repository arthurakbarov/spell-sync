# Efficient staged testing

Canonical guide for selecting validation during spell-sync development.

**Principle:** local edit speed beats local completeness. Full CI with coverage is a
**publish/release** property, not an every-commit property.

Prefer **behavioral and invariant tests** over line-execution padding. When a new line is
uncovered, add or extend a non-`*coverage*` test first; grow frozen `*coverage*` suites only
with explicit owner approval (see `tests/test_padding_inventory_policy.py`, residual R-PWR).

## Coverage and suite shape

| Keep strict | Do not grow | Add where missing |
|-------------|-------------|-------------------|
| Mutation safety clusters at commit gate | Legacy `*coverage*` padding inventory | Property/idempotence tests for Pull union and Push subsets |
| Publish coverage: **100% lines** / **≥90% branches** on `application/` + mutation paths; **≥98% lines** on TUI/presentation/remainder (`scripts/coverage_policy.py`) | Fragile skill-prose substring contracts (prefer paths/headings/frontmatter) | Real-app manual samples before publish (R-CON) |
| Installed-wheel smoke on publish | Full CI after every polish commit | Windows hardware adversarial when available (R-WIN) |

**Freeze + shrink:** do not raise `MAX_COVERAGE_NAMED_TEST_DEFS`. When refactoring, move
coverage into behavioral modules and delete padding tests so the ceiling can drop later.

**Property tests:** `tests/test_sync_invariants_property.py` (Hypothesis) covers casefold
Pull union absorption/commutativity/associativity, Push subset filters, and synthetic
Pull → Push → Pull stability. Keep examples bounded; do not replace safety integration tests.

**Writer goldens:** `tests/test_writer_goldens.py` + `tests/goldens/writers/` snapshot Chrome,
Firefox/text, Hunspell, JetBrains XML, and Sublime JSON outputs. Update goldens only when
writer format intentionally changes.

**CLI startup budget:** `tests/test_cli_import_surface.py` asserts Textual stays unloaded on
`import spell_sync.cli` and cold `status --json` stays under catastrophic budgets (750ms /
2500ms).

**Crash mid-journal:** `TestCrashRecoveryMatrix` includes target `write_started` without
`write_completed` (post-image → restore). Do not grow coverage-padding for more crash points.

**Publish sampling (R-CON):** before owner publish, record at least three real-application
manual validations on the primary maintainer OS (recommended first sample: Chrome, Firefox,
system spelling) via skill `platform-validation`. Synthetic CI is not a substitute. Current
sample includes chrome/macos and macos_spelling/macos (read-only discovery + push plan).

**Windows adversarial (R-WIN):** R1–R7 remain owner hardware only — not simulated in CI.

**History compaction tests** use the shared `history_record_cap` fixture
(`tests/history_test_utils.py`) so full CI does not spend seconds writing 500+ JSONL rows
per case.

## Two local modes

```text
Local minimal (every edit + every local commit, no coverage)
→ continue editing
→ Full (once before push/release or explicit owner “final”; hard wall ≤20 min)
```

Do not loop:

```text
full CI → tiny edit → full CI → format fix → full CI
```

### Local minimal — default

```bash
python3 scripts/run_dev_loop.py
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_ci_necessity.py --purpose local --explain
```

Runs only:

1. Changed-module / affected pytest targets **without coverage**
2. `ruff check` / `ruff format --check` on touched Python
3. `scripts/check_architecture.py --check` when application boundaries change
4. Mapped validators from the test-impact registry

Does **not** run: full CI, packaging wheel-smoke, environment suite, entire TUI group fan-out,
coverage policy, or mandatory pre-final polish.

**Edit loop** (`run_dev_loop.py` without flags): affected module scope, wall **≤60s** strict.

**Commit gate** (`run_dev_loop.py --commit-gate`): same affected module scope plus **safety
cluster tests** when mutation paths change (pull/push/transaction/recovery). Wall **≤120s**
strict (affected work + ~1 min tooling overhead). If exceeded, shrink scope — do **not**
escalate to full CI.

Shared-fixture edits do **not** fan out to all pytest clusters in local minimal mode
(deferred to full CI).

| Change class | Local minimal gate |
|--------------|-------------------|
| Product (`spell_sync/**`, non-TUI) | Affected module tests + validators |
| TUI | Touched TUI module tests + validators |
| Tooling / CI scripts / test-impact | Dev-tooling slice + validators |
| Docs / agent only | docs-contract + agent-config |
| Packaging / `pyproject` | Dependency + environment validators (**not** wheel-smoke) |
| Mutation paths (pull/push/transaction/recovery) | Commit gate adds safety **cluster** tests |

Expected necessity for normal local product work:

| Result | Action |
|--------|--------|
| `commit-gate-sufficient` | Local minimal only; **do not** run full CI |
| `lightweight-sufficient` | `python3 scripts/run_lightweight_validation.py` |
| `no-action` | Skip redundant validation |
| `full-required` | Rare locally (unknown classification); treat as full CI |

### Full — publish / release / explicit final

```bash
python3 scripts/check_ci_necessity.py --purpose publish --explain
scripts/ci.sh
python3 scripts/check_ci_evidence.py
# release / signed artifacts:
python3 scripts/check_ci_evidence.py --release
```

Full CI includes grouped pytest **with** tiered coverage (`scripts/coverage_policy.py`:
100% lines on application + mutation paths; ≥98% lines on TUI/presentation/remainder;
≥90% branches on strict paths (presentation/remainder: lines only)), packaging,
wheel-smoke, and all validators. Agent runs full CI only on explicit owner request
(“готов к push/release”) or via `release-candidate` / publish workflows.

Hard safety wall: **≤1200s (20 min)** via execution-controller profile `full-ci`. Soft/expected
timings remain for tracking only — functional failure or hard-cap termination is the stop
condition, not exceeding expected duration.

## Legacy level names

Older docs referred to Level 0–3 or L0 / L1 / L2. Mapping:

| Old | New |
|-----|-----|
| Level 0 / L0 micro | Local minimal edit loop (`run_dev_loop.py`) |
| Level 1 / L1 commit gate | Local minimal commit gate (`--commit-gate`) |
| Level 2 | *(removed — commit gate replaced the middle cluster fan-out)* |
| Level 3 / L2 full CI | Full (`scripts/ci.sh`) |

Clusters remain defined in `tests/test-impact.toml` (runtime, pull, push, transaction,
recovery, tui, …). Safety-critical clusters use **cluster** tests at commit gate only when
mutation paths change; ordinary local minimal scope stays at **module** tests.

## Planner and runners

| Tool | Purpose |
|------|---------|
| `scripts/run_dev_loop.py` | Default local minimal entry (no coverage, no edit-loop block) |
| `scripts/test_plan.py` | Select targets (`--dev-scope` for local minimal) |
| `scripts/run_focused_tests.py` | Heavier focused runner (budget-controlled); prefer `run_dev_loop` for edits |
| `tests/test-impact.toml` | Production → test mapping |
| `ci/test-groups.toml` | Full-CI pytest groups |
| `.artifacts/test-runs/current.json` | Focused-run evidence (gitignored) |

```bash
python3 scripts/test_plan.py --dev-scope --explain
python3 scripts/run_dev_loop.py
python3 scripts/run_dev_loop.py --commit-gate
```

With `--dev-scope`, planner level `cluster` downgrades to **module** tests unless a
safety-critical cluster is required (commit gate passes `include_safety_cluster_tests`).

## Necessity planner

```bash
# Agent / local default
python3 scripts/check_ci_necessity.py --purpose local --explain

# Before push / release
python3 scripts/check_ci_necessity.py --purpose publish --explain
```

| Purpose | Product/test/toolchain change |
|---------|-------------------------------|
| `local` | `commit-gate-sufficient` |
| `publish` | `full-required` |

Full CI evidence (`ciInputDigest`) remains required for publish/release. Exact Git HEAD
matching remains required for release, publication, and signed artifacts.

## Time budgets (SLA)

| Mode | Wall SLA | Expected / tracking | When |
|------|----------|---------------------|------|
| Local minimal edit | **≤60s** strict | same as SLA | every edit |
| Local minimal commit gate | **≤120s** strict | same as SLA | every local commit |
| Full CI | **≤1200s** hard safety | expected from `gate:full-ci` plan; compare actual | push/release / explicit final |

`run_dev_loop.py` prints `DEV_LOOP_BUDGET_SECONDS`, `DEV_LOOP_WALL_SECONDS`, and
`DEV_LOOP_BUDGET_STATUS=within|exceeded`. Exceed without `--ignore-budget` exits `2`
(functional failures still exit `1`). Shrink scope — do **not** escalate to full CI.

### Full expected tracking

Full CI may take as long as needed to finish correctly within the hard safety cap. Still:

1. Before run: note `ExecutionPlan` expected / soft from `tests/execution-budget.toml`
   profile `full-ci` (and any learned expected printed by the controller).
2. After run: compare wall time to expected and soft (`success-slow` when beyond soft).
3. Report: expected seconds, soft seconds, actual seconds, delta, status
   (`within-expected` | `soft-exceeded` | `hard-bound` if the safety hard cap fired).

Baseline reference (local full CI ~2026-08): wall ≈ **651s** (~11 min); registry
`initialExpectedSeconds=420`, `initialSoftSeconds=630`, `hardCapSeconds=1200`.
Re-check after each full CI run.

### Measured wall times (2026-08-04, local machine)

Single-shot samples via `scripts/run_dev_loop.py` (no coverage):

| Scenario | Edit loop | Commit gate | Notes |
|----------|-----------|-------------|-------|
| docs | 0.3s | 0.2s | validators only |
| tooling (`check_ci_necessity`) | 8.5s | 55s | agent-workflow module slice |
| push product | 1.4s | 2.3s | push + transaction module; safety at commit gate |
| TUI controller | 42s | 67s | under 60s / 120s |
| shared fixture (`conftest`) | 2.1s | 2.8s | test-selection only (no full fan-out) |
| packaging (`pyproject`) | — | 19s | validators + packaging unit; wheel-smoke deferred to full CI |

Ordinary product commit gate should stay well under **120s**.

## Docs-only and safety

Documentation edits: validators only (docs style/contract, agent config when agent docs
change).

Pull / Push / transaction / Recovery path changes always include the matching safety
cluster tests at commit gate. Adversarial suites remain mandatory before full CI publish when
those surfaces change (see historical safety table in repo tests).

## Prohibited shortcuts

Do not, for speed:

- remove assertions or lower full CI coverage thresholds
- permanently skip safety suites after mutation changes
- use `pytest --lf` or `pytest -x` as local minimal or full CI evidence
- treat local minimal as publish validation
- run packaging or wheel smoke during unrelated local minimal loops
- run full CI after every polish commit

## Execution time control

Full CI and registered expensive commands use the execution controller
(`docs/EXECUTION_TIME_CONTROL.md`). Local minimal `run_dev_loop.py` is intentionally outside the
edit-loop admission budget so micro validation is not blocked.

## Developer report

Modifying tasks should document: mode used (local minimal edit / commit gate / full), commands,
durations, `DEV_LOOP_BUDGET_*` (local minimal) or full expected vs actual, and whether full CI
was deferred. Expected full CI count per ordinary polish task: **0**. Expected before
push/release: **1**.

See `docs/AGENT_DEVELOPMENT.md` and `.cursor/skills/select-and-run-tests/SKILL.md`.
