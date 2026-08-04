# Development

Package version source of truth: `project.version` in `pyproject.toml`.

## Setup

Requires **Python 3.11+**.

Python **3.11** and **3.12** are tested in CI. Python **3.13** is experimental
(`continue-on-error` compatibility job). See [Supported environments](SUPPORTED_ENVIRONMENTS.md).

```bash
git clone https://github.com/arthurakbarov/spell-sync.git
cd spell-sync
python3 scripts/project_environment.py sync --profile full-ci
```

Do not commit personal `wordlist.txt`, `lint-whitelist.txt`, or local `spell-sync.toml` to the
public repo.

## Deterministic development workflow

Operator command table (SSOT: `config/dev-commands.json`):

[dev-commands:start]
| Task | Command | Stage |
|------|---------|-------|
| Read-only branch/dirty/necessity rollup | `python3 scripts/agent_context.py` | before-work |
| Verify maintainer environment | `python3 scripts/project_environment.py check` | before-work |
| Assess local CI necessity | `python3 scripts/check_ci_necessity.py --purpose local --explain` | commit-gate |
| Commit gate (≤120s + safety clusters) | `python3 scripts/run_dev_loop.py --commit-gate` | commit-gate |
| Local minimal validation (≤60s) | `python3 scripts/run_dev_loop.py` | edit-loop |
| Verify CI evidence for HEAD | `python3 scripts/check_ci_evidence.py` | evidence |
| Full CI (publish / owner final only) | `scripts/ci.sh` | full-ci |
| List recent failed execution spans | `python3 scripts/dev_runs.py failures` | triage |
| Show one execution/CI run | `python3 scripts/dev_runs.py show <run-id>` | triage |
| Timing / budget history report | `python3 scripts/execution_budget_report.py` | triage |
[dev-commands:end]

1. Run focused pytest for the changed scope (`docs/TESTING_STRATEGY.md`, skill
   `select-and-run-tests`).
2. Run documentation and architecture contract checks when docs or boundaries change.
3. Commit tracked changes; verify clean working tree.
4. Assess CI necessity: `python3 scripts/check_ci_necessity.py --explain`
5. When `full-required`, run full CI once on committed HEAD:

```bash
scripts/ci.sh
```

When `lightweight-sufficient`:

```bash
python3 scripts/run_lightweight_validation.py
python3 scripts/check_ci_evidence.py
```

Done-definition: [`ENGINEERING_COMPLETION.md`](ENGINEERING_COMPLETION.md) (repo/agent) and
[`PRODUCT_COMPLETION.md`](PRODUCT_COMPLETION.md) (product UX/release).

Triage failed runs (do not pipe CI through `tail`):

```bash
python3 scripts/dev_runs.py failures
python3 scripts/dev_runs.py show <run-id>
python3 scripts/execution_budget_report.py
```

Long commands print `eta: expected ~…` on stderr when display duration exceeds 5s
(`docs/EXECUTION_TIME_CONTROL.md`). Each expected interactive prompt adds a fixed **5s**
allowance to ETA / wall hard only — not to the work budget. Runs are logged and successful
samples update future estimates.
Registered development and CI commands run under execution budget control
(`docs/EXECUTION_TIME_CONTROL.md`, `tests/execution-budget.toml`). Prefer integrated runners
(`run_focused_tests.py`, `run_pre_final_checks.py`, `ci_runner.py`) over raw unbounded pytest.
Product Pull/Push/Recovery paths are not wrapped by the controller.

Before commit, optional:

```bash
python3 scripts/run_pre_final_checks.py
```

A successful full CI run exits **0** and prints:

```text
CI_RESULT=success
CI_EXIT=0
CI_SUMMARY=<absolute path>
CI_LOG=<absolute path>
```

Failures print `CI_FAILED_ID=<stable check id>`. Read `CI_SUMMARY` and `CI_LOG` — do not rely
on manual log tailing as the primary gate.

`scripts/ci.sh` delegates to `scripts/ci_runner.py`: docs style/contract, agent config, target
capabilities, **architecture boundaries** (`scripts/check_architecture.py`), ruff, mypy,
grouped pytest with **100% line** and **≥96% branch** coverage on `spell_sync/`, packaging,
installed-wheel smoke, and headless command scenarios. CI smoke uses temporary HOME and project
directories only.

Agent-oriented workflow: `docs/AGENT_DEVELOPMENT.md`.

## Static checks

Ruff covers the production package, tests, and Python scripts under `scripts/`. Mypy covers
`spell_sync/` only.

```bash
python3 -m ruff check spell_sync tests scripts
python3 -m ruff format --check spell_sync tests scripts
python3 -m mypy spell_sync
python3 scripts/check_docs_contract.py
python3 scripts/check_architecture.py --check
python3 scripts/check_agent_config.py
```

Coverage gate (**full CI / publish**): 100% lines, ≥96% branches on `spell_sync/`. Prefer
behavior and invariant tests over line-execution padding. Legacy `*coverage*` padding suites
are frozen by `tests/test_padding_inventory_policy.py` and must not grow. Ordinary edit/commit
cycles use local minimal without coverage (`docs/TESTING_STRATEGY.md`).

## JSON output

All commands support `--json` with a shared envelope:

```json
{
  "schema_version": 1,
  "command": "push",
  "exit": 0,
  "result": {}
}
```

Command-specific fields are merged at the top level (see tests in `tests/test_json_contract.py`).

## Headless scenarios

`tests/test_gui_smoke.py` runs portable CLI scenarios directly. The public repository does not
ship an interactive GUI harness.

## Version

The package version source of truth is `project.version` in `pyproject.toml`.

## Maintainer layout (optional)

Some contributors keep a private wordlist repo with a nested `spell-sync/` tool clone. That layout
is not required for hacking on the public tree.
