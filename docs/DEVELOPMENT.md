# Development

## Setup

Requires **Python 3.11+**.

Python **3.11** and **3.12** are currently tested. Classifiers list those versions; newer
Python releases may work but are not verified in CI yet.

```bash
git clone https://github.com/arthurakbarov/spell-sync.git
cd spell-sync
python3 -m pip install -e ".[dev]"
```

Do not commit personal `wordlist.txt`, `lint-whitelist.txt`, or local `spell-sync.toml` to the
public repo.

## Deterministic development workflow

1. Run focused pytest for the changed scope.
2. Run documentation and architecture contract checks when docs or boundaries change.
3. Run full CI:

```bash
scripts/ci.sh
```

A successful run exits **0** and prints:

```text
CI_RESULT=success
CI_EXIT=0
CI_SUMMARY=<absolute path>
CI_LOG=<absolute path>
```

A failure exits non-zero, prints `CI_FAILED_ID=<stable check id>`, and writes the same summary
and log paths. Read `CI_SUMMARY` and `CI_LOG` to identify the failing contract, module, and
next validation command. Do not rely on manual log tailing as the primary gate.

`scripts/ci.sh` delegates to `scripts/ci_runner.py`, which runs docs style, docs contract,
agent config, target capabilities, ruff, mypy, pytest with **100% line coverage** and at least
**96% branch** coverage on `spell_sync/`, package build, twine check, installed-wheel smoke,
lint smoke, and headless command scenarios. CI smoke uses temporary HOME and project
directories; it does not create files in the repository root.

Agent-oriented workflow details live in `docs/AGENT_DEVELOPMENT.md` (not duplicated here).

Static checks: Ruff covers the production package, tests, and Python scripts under
`scripts/`. Mypy covers the production package only (`spell_sync/`).

```bash
python3 -m ruff check spell_sync tests scripts
python3 -m ruff format --check spell_sync tests scripts
python3 -m mypy spell_sync
python3 -m pytest tests -q --cov=spell_sync --cov-branch --cov-fail-under=98
python3 scripts/check-docs-contract.py
python3 -m build
python3 -m twine check dist/*
python3 -m pytest tests/test_gui_smoke.py -q
```

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
