# Development

## Setup

Requires **Python 3.11+**.

```bash
git clone https://github.com/arthurakbarov/spell-sync.git
cd spell-sync
python3 -m pip install -e ".[dev]"
```

Do not commit personal `wordlist.txt`, `lint-whitelist.txt`, or local `spell-sync.toml` to the
public repo.

## Checks

```bash
scripts/ci.sh
```

Runs: docs style, ruff, mypy, pytest with **100% line coverage** and at least **96% branch
coverage** on `spell_sync/`, wheel build, twine check, lint smoke, and headless command scenarios.
The branch threshold is intentionally lower than the line threshold because platform-specific
defensive branches are not all executable on every CI host.

Individual steps:

```bash
python3 -m ruff check spell_sync tests
python3 -m ruff format --check spell_sync tests
python3 -m mypy spell_sync
python3 -m pytest tests -q --cov=spell_sync --cov-branch --cov-fail-under=98
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

Single source: `version` in `pyproject.toml` (currently **0.1.0**).

## Maintainer layout (optional)

Some contributors keep a private wordlist repo with a nested `spell-sync/` tool clone. That layout
is not required for hacking on the public tree.
