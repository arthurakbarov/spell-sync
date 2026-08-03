---
name: installed-wheel-smoke
description: >-
  Verify spell-sync works from an installed wheel outside the source checkout.
  Use before release candidates or when packaging changes. Editable install is
  not sufficient.
---

# Installed wheel smoke

## When to use

- After packaging changes (`pyproject.toml`, bundled resources, TCSS)
- Before release candidate sign-off
- When verifying TUI resources ship in the wheel

## Do not use

- Editable install (`pip install -e .`) as the only packaging check — CI wheel smoke is minimal
- Real application dictionaries or maintainer wordlist

## Workflow

1. Clean build artifacts and build wheel/sdist:

```bash
rm -rf build dist
python3 -m build
python3 -m twine check dist/*
```

2. Inspect wheel contents — no tests, caches, logs, personal config:

```bash
unzip -l dist/*.whl
```

3. Create clean venv, temporary HOME, cwd **outside** repository:

```bash
smoke_home="$(mktemp -d)"
smoke_cwd="$(mktemp -d)"
python3 -m venv /tmp/spell-sync-smoke-venv
/tmp/spell-sync-smoke-venv/bin/pip install dist/*.whl
cd "$smoke_cwd"
HOME="$smoke_home" /tmp/spell-sync-smoke-venv/bin/spell-sync --help
HOME="$smoke_home" /tmp/spell-sync-smoke-venv/bin/spell-sync version
HOME="$smoke_home" /tmp/spell-sync-smoke-venv/bin/spell-sync support-report --format json
```

4. Verify TUI import and bundled resources (TCSS, examples) load from installed package.
   Exercise Target Details, Health → Export support report, and Review session Save report when validating 0.3.0+ transparency features.

5. Optional: run `tests/test_installed_workflow.py` — automated end-to-end smoke (includes `support-report`).

6. Confirm no network calls and no real user data touched.

## Stop conditions

- Wheel installs cleanly outside checkout
- CLI help and version work
- No forbidden files in wheel
- Automated smoke test passes if run

## Final report

- Wheel path and version
- Forbidden-content scan result
- Commands exercised
- Failures with stderr if any
