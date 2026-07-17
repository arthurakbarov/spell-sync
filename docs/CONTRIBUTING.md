# Contributing

Thanks for improving spell-sync. Small, focused pull requests are easier to review.

## Setup

See [Development](DEVELOPMENT.md). Requires Python **3.11+**.

```bash
pip install -e ".[dev]"
scripts/ci.sh   # must exit 0
```

## Pull requests

1. Describe behavior change (not internal iteration history).
2. Run `scripts/ci.sh` locally.
3. Update user docs if CLI, config, or recovery behavior changes.
4. Do not commit personal wordlists or maintainer-only paths.

## Security

Report vulnerabilities per [.github/SECURITY.md](../.github/SECURITY.md).

## Versioning

Stable releases are tagged `vX.Y.Z` on `main`. Release notes live in GitHub releases only.
