# Contributing

Thanks for improving spell-sync. Small, focused pull requests are easier to review.

## Setup

Requires **Python 3.14** (canonical pin: **3.14.6** via `.python-version`).

```bash
uv sync --locked --all-groups
```

See [Supported environments](SUPPORTED_ENVIRONMENTS.md).

## Validation

Prefer a focused pytest selection while editing, then run the same gates as
`.github/workflows/ci.yml` before opening a PR (or rely on GitHub Actions):

```bash
uv run python scripts/check_architecture.py --check
uv run python scripts/validate_repository_consistency.py
uv run python scripts/scan_privacy_tree.py
uv run python scripts/audit_dead_code.py
uv run python scripts/check_target_capabilities.py --check
uv run python scripts/validate_doctor_schema.py
uv run python scripts/validate_target_validation_schema.py
uv run ruff check spell_sync tests && uv run ruff format --check spell_sync tests
uv run mypy spell_sync
uv run pytest tests -q
uv build && uv venv /tmp/spell-sync-wheel \
  && uv pip install --python /tmp/spell-sync-wheel dist/*.whl \
  && /tmp/spell-sync-wheel/bin/spell-sync version
```

## Pull requests

1. Describe the behavior change for users and reviewers.
2. Update user docs if CLI, config, Collect/Update, or Recovery behavior changes.
3. Do not commit personal wordlists or private config.

## Code of conduct

See [.github/CODE_OF_CONDUCT.md](../.github/CODE_OF_CONDUCT.md).

## Security

See [.github/SECURITY.md](../.github/SECURITY.md). Report vulnerabilities privately via
GitHub Security Advisories.
