# Execution time control

Canonical guide for bounded development commands: admission before execution, immutable
timing plans, persistent local history, and owned process termination.

This infrastructure applies to **toolchain and validation runners only**. Product Pull, Push,
Recovery, and other mutation paths are not wrapped by the execution controller.

## Goals

Development methodology must answer four questions before and during expensive commands:

```text
1. Should the selected check run now?
2. How long should this specific invocation take?
3. Is there demonstrated progress after start?
4. When should waiting stop and investigation begin?
```

The system prevents:

- full CI after every small edit
- repeated broad test runs on an unchanged tree
- re-execution when functional evidence is already valid
- duplicate active executions of the same workload
- unbounded `subprocess` waits
- treating PID existence as progress
- infinite stdout that prolongs waiting
- automatic parent retry after timeout
- automatic hard-cap increases after hangs
- learning normal duration models from failed, aborted, or timed-out runs
- gradual acceptance of performance regressions
- unbounded timeout diagnostic collectors
- orphan child or grandchild processes
- loss of the exact child check that stopped a parent gate

Primary business goal:

```text
Testing after a small change must not consume most of the edit loop.
No registered expensive development command may wait without a bound.
```

## Decision order

Before test or CI execution:

```text
CI necessity
→ reusable functional evidence
→ duplicate active execution
→ execution-cost admission
→ immutable timing plan
→ execution
```

Functional evidence and timing prediction use separate identities:

| Question | Owner |
|----------|-------|
| Must the check rerun because inputs changed? | Functional evidence (`check-ci-evidence`, test ledger, CI necessity) |
| How long will a required check take and when should it stop? | Execution controller |

Reusing functional evidence:

- does not launch the command
- does not create a fake duration sample
- records `EXECUTION_RESULT=reused`
- may account estimated time saved in session totals

Timing policy changes (registry or formula only) invalidate prior timing predictions but do
not automatically invalidate functional green evidence. CI-impact classification remains
canonical for what counts as a CI-relevant change.

## Module map

Stdlib-only package under `scripts/execution_control/`:

| Module | Role |
|--------|------|
| `models.py` | `ExecutionPlan`, `ExecutionRunResult`, `SpanRecord`, status and admission enums |
| `state_paths.py` | Local execution-control state and artifact paths |
| `snapshot_workspace.py` | Snapshot workspace layout resolution |
| `registry.py` | Load and validate `tests/execution-budget.toml` |
| `identity.py` | Workload and policy fingerprints, normalized signature |
| `context.py` | Platform, Python, workload bucket, coverage/TUI/packaging flags |
| `history.py` | SQLite spans, leases, learning samples, admin audit |
| `statistics.py` | Median, percentiles, MAD, confidence labels |
| `prediction.py` | Expected, soft, stall, hard thresholds from history |
| `admission.py` | CI necessity integration, edit-loop budget, reuse |
| `progress.py` | Progress contracts for stall observation |
| `process_tree.py` | Owned process-group execution and termination |
| `diagnostics.py` | Bounded timeout investigation bundles |
| `controller.py` | Immutable plan, run, classify, persist span |
| `gate_controller.py` | Parent gate lifecycle, linked child spans, wall duration |
| `plan_preview.py` | Pure child `ExecutionPlan` preview without subprocess or lease |
| `aggregate_plan.py` | Parent expected/soft/hard from concrete child plan sums |
| `gate_admission.py` | Aggregate admission after child previews |
| `gate_previews.py` | Bounded planner → previews → aggregate gate open |
| `planning_supervisor.py` | Bounded planner execution without parent gate lease |
| `reporting.py` | Machine-readable `EXECUTION_*` stdout lines |
| `session.py` | Edit-loop test-time share and regression warnings |
| `budget_analysis.py` | History/registry report payload for CLI reporting |
| `mappings.py` | Stable execution IDs for CI checks and gates |

CLI entry points:

| Script | Purpose |
|--------|---------|
| `scripts/run_with_budget.py` | Run an arbitrary registered command under budget |
| `scripts/execution_budget_report.py` | Report history and registry summary |
| `scripts/execution_budget_admin.py` | Accept or reject learning samples |
| `scripts/validate_execution_budget.py` | Registry and integration contract validator |
| `scripts/run_snapshot_tests.py` | Snapshot gate with parent/child execution control |

Registry: `tests/execution-budget.toml`.

## Parent gates and admission

Parent gates open only after a **two-stage lifecycle**:

1. **Bounded planning supervisor** (`focused:planner`, `pre-final:planner`, or CI child preview
   list) produces a concrete child plan without acquiring the final parent gate lease.
2. **Pure child previews** (`preview_execution_plan`) build immutable child `ExecutionPlan`
   values without subprocess, lease, history observation, or artifact mutation.
3. **Aggregate parent plan** derives `expectedSeconds`, soft, and hard from
   `sum(child expected) + max(10s, 10% orchestration overhead)` and stores
   `childPlanDigest`, `plannedChildCount`, `plannedExpectedSum`, and related fields.
4. **Admission** (`assess_gate_admission`) evaluates aggregate cost, edit-loop budget, session
   test-time share, and functional evidence reuse — then acquires the parent gate lease.
5. **Execution** runs immutable child plans via `run_child_with_plan`.

Parent gates (`gate:full-ci`, `gate:pre-final`, `gate:focused-*`, `gate:snapshot-tests`) record
parent wall duration at finish and link each child span via shared `run_id` and `parent_span_id`.
Final CI parent timing must satisfy
`expectedSeconds ≈ plannedChildExpectedSum + plannedOrchestrationOverhead` (rounded, capped).

Admission decisions are enforced before subprocess launch:

| Decision | Behavior |
|----------|----------|
| `run` | Acquire lease, persist plan, execute |
| `reuse` | Skip subprocess; no duration sample |
| `narrow` | Block broad command; emit replacement plan; no subprocess |
| `defer-to-pre-final` | Block until pre-final gate |
| `reject-duplicate` | Block duplicate active lease |
| `block-controller-error` | Block on controller error |

Each immutable plan stores `contextSignature` used for exact-history learning at span write time.
Child spans never rebuild context from `profile_id` alone.

Parent hard limits are enforced at runtime: each child receives
`min(child hard, parent remaining)` and the owned-process supervisor terminates the active tree
when the parent deadline elapses. Orchestration between children (planner execution, result
serialization, terminal summary) is bounded by the same parent deadline via
`check_orchestration_budget()`. `finish_gate()` is exactly-once; failed children mark gate
state but do not finalize the parent span.

Hard timeout termination captures an immutable ownership snapshot (root PID, owned process group,
descendant identities with start markers) **before** the first signal, then terminates the
owned group and captured detached descendants. PID-only reuse is not trusted.

`KeyboardInterrupt` marks the active child and parent as `interrupted` with exit `130`; parent
gates never finish as `success` after an interrupted child.

Timeout diagnostics run entirely inside killable collector processes under one monotonic
deadline. After collector timeout the controller never performs synchronous `ps`, descendant
scan, mkdir, serialization, or file write; incomplete results are reported explicitly.

Focused and pre-final gates run bounded planner children (`focused:planner`, `pre-final:planner`)
**before** parent gate admission. Snapshot gates require explicit `--workspace-root` and
`--output`; public pytest must not mutate the owner workspace archive path. Pre-gate `bootstrap.python`
uses a committed 30s subprocess timeout before full CI gate children start.

`ci:pytest` uses the dedicated `ci-pytest` profile (measured full-suite evidence). Fast CI
validators use `ci-validator`; generic `ci-child` hard remains 300 seconds.

Progress contracts mark progress only on semantic transitions (pytest node results, CI child
events, structured phases, artifact state). Arbitrary stdout growth is not progress.

## Stable execution identity

Each monitored invocation has a stable `execution_id`:

| Kind | Examples |
|------|----------|
| Gate | `gate:focused-module`, `gate:focused-cluster`, `gate:pre-final`, `gate:full-ci` |
| CI child | `ci:pytest`, `ci:mypy`, `ci:ruff-check`, … |
| Focused child | `focused:pytest`, `focused:static`, … |
| Diagnostic | `diagnostic:pytest` |
| Fallback | `gate:unknown` |

Child mappings in the registry link child IDs to profiles and parent gates.

## Fingerprints

### Workload fingerprint

Hash of execution ID plus normalized workload payload: command script name, mode, test file
and node counts, cluster IDs, coverage/TUI/packaging flags. Changes when the actual work
changes.

### Policy fingerprint

Hash of registry digest, profile ID, progress contract, hard cap, and controller schema
version. Changes when timing policy changes without necessarily changing workload.

### Normalized signature

Short hash combining execution ID, workload fingerprint, and normalized context signature.
Used for duplicate-active detection and exact cohort lookup.

Policy and workload fingerprints are stored separately so policy updates preserve prior
duration samples where appropriate.

## Immutable execution plan

Before subprocess start the controller builds a frozen `ExecutionPlan`:

- `run_id` — unique run identifier
- threshold triple: `expected_seconds`, `soft_seconds`, `stall_seconds` (optional), `hard_seconds`
- `diagnostic_hard_seconds`, `termination_grace_seconds`
- `progress_contract_id`, `termination_policy_id`
- prediction metadata: source, confidence, sample count
- `admission_decision`

The plan is serialized to a bounded local artifact under the state directory and printed via
`EXECUTION_*` lines. **The running plan is never recalculated.** New history samples affect
only the next execution.

## Thresholds

| Threshold | Meaning |
|-----------|---------|
| Expected | Predicted normal duration; informational baseline |
| Soft | Overrun boundary; success beyond soft → `success-slow` (quarantined from learning) |
| Stall | Optional; no semantic progress for this interval after soft (profile-dependent) |
| Hard | Absolute termination bound; enforced in Stage 1+ |

Prediction sources (fallback order):

1. Exact cohort — same execution ID, workload fingerprint, context signature
2. Workload history — same workload fingerprint, any context
3. Profile history — same execution ID, any workload
4. Registry defaults — profile `initial*` values

Expected duration blends registry initial values with learned median (weight ramps with
sample count up to ten samples). Soft and hard thresholds use robust statistics (median,
p90, MAD-based sigma) capped by profile and global hard limits.

Hard caps change only through committed registry updates. The controller never auto-increases
limits after timeouts.

## Learning policy

### Automatic normal learning

A span is accepted for learning when:

- exit code is zero
- status is `success` (duration ≤ soft)
- not quarantined

### Slow-success quarantine

Runs with status `success-slow` complete successfully but are not accepted for normal
learning (`EXECUTION_LEARNING_ACCEPTED=false`, quarantine reason `soft-overrun`).

### Censored observations

These never train the normal duration model:

- `failed`
- `timeout-hard`, `timeout-stall`
- `interrupted`
- `blocked-duplicate`, `blocked-admission`

Explicit admin accept/reject via `scripts/execution_budget_admin.py` can override quarantine
when justified.

## SQLite history

Local persistent store outside the repository:

```text
$XDG_STATE_HOME/spell-sync/execution-control/history.sqlite3
```

Fallback: `$HOME/.local/state/spell-sync/execution-control/history.sqlite3`.

Schema stores span records, active leases, and admin audit entries. WAL mode with busy timeout.
Per-execution-ID retention keeps the most recent 500 spans.

On corruption the database is quarantined and recreated; history updates are marked degraded
but execution may continue.

Timing state must not appear in owner snapshots, wheels, or public commits.

## Progress contracts

Stall-sensitive profiles reference a tested progress contract:

| Contract | Typical use |
|----------|-------------|
| `pytest-node-transition` | Pytest node completion lines |
| `ci-child-transition` | CI check pass/fail markers |
| `structured-phase-transition` | Full CI phase banners |
| `artifact-state-transition` | Snapshot and evidence markers |

Valid progress includes new pytest nodes, child check transitions, structured phase markers,
and bounded semantic output changes.

**Not** valid progress:

- PID or CPU existence alone
- repeated identical lines (capped at 50 repeats)
- wrapper heartbeat timestamps
- unbounded stdout without semantic transition

Stall enforcement (Stage 2) is enabled per profile only after contract tests pass. Hard
deadlines remain absolute regardless of output volume.

## Parent and child spans

Parent gates (`gate:full-ci`, `gate:focused-cluster`, …) orchestrate child checks. Each child
receives its own immutable plan and hard bound.

Parent expected duration is derived from child plans plus orchestration overhead. Parent hard
is capped by profile limits.

On child timeout:

```text
terminate child owned tree
→ record exact child execution ID
→ stop parent orchestration
→ do not wait for parent hard limit
```

A bounded parent must never launch an unbounded child.

CI summary includes a parent timing block and per-check child timing blocks. Child timeout
sets `CI_FAILED_ID=execution.hard-timeout` and `CI_TIMEOUT_CHECK_ID=<stable child id>`.
Timeout never counts as CI success. Timing metadata does not weaken `finalEvidence`,
`treeStable`, or `ciInputDigest` checks.

## Process ownership

Monitored commands run in a new process session (`start_new_session=True`). Termination uses
owned process-group signals (`SIGTERM`, grace period, then `SIGKILL`). Unrelated processes
are never signaled.

The controller captures stdout/stderr tails for diagnostics but does not modify child
arguments, working directory, test selection, functional environment (except controller-owned
variables), output content, exit codes, or repository files.

Overhead target for commands ≥ 1 s: `≤ max(100 ms, 2%)`.

## Admission

`scripts/execution_control/admission.py` integrates with `scripts/check_ci_necessity.py`.

Admission decisions:

| Decision | Meaning |
|----------|---------|
| `run` | Execute with immutable plan |
| `reuse` | Valid functional evidence; skip execution |
| `narrow` | Predicted edit-loop cost too high; reduce scope |
| `defer-to-pre-final` | Defer optional check to pre-final gate |
| `reject-duplicate` | Same workload already active |
| `block-controller-error` | Controller or history failure |

Rules:

- Required safety checks cannot be dropped solely because of predicted duration
- Full CI runs only when CI necessity is `full-required`, as final gate, or on explicit owner request
- Optional edit-loop checks may be reused, narrowed, or deferred

### Edit-loop budget

Registry meta `editLoopBudgetSeconds` (default 120 s). When predicted optional focused cost
exceeds the budget, admission may narrow or defer optional scope and explains the decision.
Required safety clusters are never dropped for budget reasons. The final required gate is
never skipped for budget reasons alone.

### Session cost accounting

`session.py` tracks focused, pre-final, full CI, and diagnostic seconds within a sliding
window. When test time exceeds `sessionTestTimeShareWarn` (default 60%) of edit time, the
controller prints `EXECUTION_WARNING=test-time-dominates-edit-loop`.

## Duplicate protection

Before execution the controller acquires a SQLite-backed lease on `normalized_signature`.
If the same workload is already active and the owner PID is alive:

```text
EXECUTION_RESULT=blocked
EXECUTION_FAILED_ID=execution.duplicate-active
EXECUTION_OWNER_PID=...
```

The second command does not start. Stale leases are cleared when the owner PID is gone.

## Evidence reuse

Two layers cooperate:

1. **Functional evidence** — test ledger, CI evidence, CI necessity (`no-action`,
   `lightweight-sufficient`)
2. **Timing reuse** — admission returns `reuse` without subprocess start

Reuse prints `EXECUTION_RESULT=reused` and creates no duration sample.

## Retry limits

Registry profiles enforce:

- `parentRetries = 0` — no automatic parent retry after timeout
- `diagnosticRetries ≤ 1` — at most one narrow diagnostic retry after investigation

After repeated timeout the agent must fix root cause and commit before a new final gate — not
loop broad reruns.

## Diagnostic budget

On hard or stall timeout the controller collects a bounded investigation bundle under:

```text
$XDG_STATE_HOME/spell-sync/execution-control/timeouts/<run-id>/bundle.json
```

Collection hard budget: `diagnosticHardSeconds` (≤ 15 s, default 10 s). A hung collector
must not delay termination.

Bundle includes: immutable plan, active child ID, bounded stdout/stderr tails (redacted),
progress counts, timeout kind, recommended narrow diagnostic command, collector failures.

Excluded: full environment, HOME, user words, raw config, credentials, unlimited output.

## Rollout stages

Mechanisms roll out incrementally:

| Stage | Scope |
|-------|-------|
| 0 — observation | Identities, history, plan, prediction, reporting, child spans; hard fallback only |
| 1 — hard enforcement | Hard termination for focused runner, pre-final, full CI children, snapshot tests |
| 2 — stall enforcement | Per-profile, only after green progress-contract tests |
| 3 — admission control | Cost planning, duplicates, reuse, session share, narrow/defer |
| 4 — factor refinement | Documented extension process; no automatic multiplicative factor learning in initial rollout |

Current implementation: Stage 1 hard enforcement active; stall enforcement opt-in via
`--enforce-stall`; admission and reuse integrated.

## Integration points

| Runner | Gate execution ID |
|--------|-------------------|
| `scripts/run_focused_tests.py` | `gate:focused-module` or `gate:focused-cluster` |
| `scripts/run_pre_final_checks.py` | `gate:pre-final` |
| `scripts/ci_runner.py` | `gate:full-ci` parent; per-check child IDs |

Partial CI modes (`--only`, `--from`, `--resume-failed`) bypass the controller for faster
diagnostic loops. Only `mode=full` uses bounded child execution.

Direct invocation:

```bash
python3 scripts/run_with_budget.py \
  --execution-id gate:focused-module \
  --test-files 3 \
  -- python3 -m pytest tests/test_example.py -q
```

## Privacy

- State directory and SQLite database live outside the repository
- Timeout bundles redact known private path and config sentinels
- No telemetry, networking, or remote timing storage
- Owner snapshot archives must exclude timing database and timeout bundles
- `.artifacts/` remains gitignored for in-repo evidence only

## Non-interference

The controller is observability and bounds only. It must not alter product behavior, CLI/JSON
contracts, Pull/Push/Recovery semantics, or functional test outcomes. Validation evidence
remains authoritative via:

```bash
python3 scripts/check_ci_evidence.py
```

Dynamic CI run identifiers belong in generated artifacts only — not in tracked documentation.

## Validators and tests

Registry and boundary contracts:

```bash
python3 scripts/validate_execution_budget.py
```

Focused test suites: `tests/test_execution_*.py`.

Agent workflow: skill `run-time-controlled-command`, rule
`.cursor/rules/execution-time-control.mdc`.

See also `docs/TESTING_STRATEGY.md`, `docs/AGENT_DEVELOPMENT.md`.
