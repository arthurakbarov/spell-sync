---
name: privacy-export
description: >-
  Scan artifacts and repository content before handoff or publication. Use before
  creating ZIP archives, sharing wheels, or any push the owner requests. Never
  archive a parent workspace.
---

# Privacy export

## When to use

- Before sharing source ZIP, wheel, or sdist
- Before any push the owner explicitly requests
- Release candidate privacy verification

## Do not use

- To read or copy a maintainer wordlist into public artifacts
- To zip a parent directory containing private repos

## Checklist

- [ ] Operate only from public repository root
- [ ] Source via `git archive` — never whole-workspace zip
- [ ] No `.git` in handoff artifacts unless intentionally requested
- [ ] No private wordlist, personal config, or lint whitelist
- [ ] No absolute personal paths, credentials, tokens, or private emails
- [ ] No logs, operation history, journal, or snapshots
- [ ] No build caches (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist/`, `build/`)
- [ ] Inspect ZIP/wheel/sdist file list before handoff
- [ ] Calculate SHA-256 for each artifact

## Scan commands

```bash
git ls-files | grep -iE 'wordlist\.txt|spell-sync\.toml|lint-whitelist|\.log|operation-history|journal|snapshots' && exit 1 || true

git grep -iE 'private maintainer workspace|private wordlist|nested spell-words' \
  -- AGENTS.md .cursor docs README.md || true
```

Each hit must be fixed or justified before handoff.

## Stop conditions

- All checklist items pass
- Artifact contents inspected
- SHA-256 recorded

## Final report

- Artifacts inspected (paths)
- Privacy scan hits (fixed or justified)
- SHA-256 hashes
- Explicit confirmation: no private data in artifacts
