# Contributing

Thanks for improving spell-sync. Small, focused pull requests are easier to review.

## Setup

See [Development](DEVELOPMENT.md). Requires Python **3.11+** (maintainer canonical: 3.12.13).

```bash
python3 scripts/project_environment.py sync --profile full-ci
```

## Validation during development

Do **not** run full `scripts/ci.sh` after every edit. Prefer the staged ladder:

1. Exact failing test (Level 0)
2. `python3 scripts/run_focused_tests.py` (module, then cluster)
3. `python3 scripts/run_pre_final_checks.py` before commit
4. One full `scripts/ci.sh` on a clean committed tree when
   `python3 scripts/check_ci_necessity.py --explain` says `full-required`

Docs-only changes: `python3 scripts/check_docs_contract.py` and
`python3 scripts/check_agent_config.py` (when agent docs or `.cursor/` change).

Details: [Testing strategy](TESTING_STRATEGY.md), [Agent development](AGENT_DEVELOPMENT.md).

## Pull requests

1. Describe behavior change (not internal iteration history).
2. Run the staged validation above; full CI once when necessity requires it.
3. Update user docs if CLI, config, or recovery behavior changes.
4. Do not commit personal wordlists or maintainer-only paths.

## Code of conduct

See [.github/CODE_OF_CONDUCT.md](../.github/CODE_OF_CONDUCT.md).

## Security

Report vulnerabilities per [.github/SECURITY.md](../.github/SECURITY.md).

## Versioning

Stable releases are tagged `vX.Y.Z` on `main`. Release notes live in GitHub releases only.
