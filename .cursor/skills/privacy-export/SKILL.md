---
name: privacy-export
description: >-
  Scan artifacts and repository content before publication or release candidate review. Use before
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
- [ ] No `.git` in distribution artifacts unless intentionally requested
- [ ] No personal wordlist or personal `spell-sync.toml` at repository root
- [ ] No personal lint whitelist. The tracked bundled runtime whitelist is allowed and must remain packaged.
- [ ] No absolute personal paths, credentials, tokens, or private emails
- [ ] No logs, operation history, pending journal data, or transaction snapshots in tracked files or artifacts
- [ ] No exported support or review session reports in tracked files
- [ ] No build caches (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist/`, `build/`)
- [ ] Inspect ZIP/wheel/sdist file list before publication
- [ ] Calculate SHA-256 for each artifact

## Allowed public resources

These tracked package resources are expected and must remain:

```text
spell_sync/bundled/lint-whitelist.txt
spell_sync/bundled/spell-sync.toml.example
spell_sync/bundled/wordlist.txt.example
```

Source modules and tests with `journal` in the filename are allowed, for example
`spell_sync/push_journal.py` and `tests/test_push_journal.py`.

## Scan workflow

### Tracked repository files

Run the structural validator — it checks exact forbidden root/state paths without
substring false positives:

```bash
python3.11 scripts/check-agent-config.py
```

Policy summary:

| Allowed | Forbidden as personal/generated |
|---------|----------------------------------|
| bundled examples and runtime whitelist | root `wordlist.txt` |
| `spell_sync/push_journal.py`, `journal_schema.py` | root `spell-sync.toml` |
| journal-related tests | root `lint-whitelist.txt` |
| docs mentioning Recovery journal | `operation-history.jsonl`, `operation-history.lock` |
| | root `snapshots/`, root `journal/` state dirs |
| | root `*.log` |

### Agent configuration content

```bash
git grep -iE 'private maintainer workspace|private wordlist|nested spell-words' \
  -- AGENTS.md .cursor docs README.md || true
```

Each hit must be fixed or justified before publication.

### Artifact contents

Inspect ZIP, wheel, and sdist listings separately. Artifacts must not contain tests,
caches, personal config, wordlist, history, journal data, or snapshots.

## Stop conditions

- All checklist items pass
- Structural validator green
- Artifact contents inspected
- SHA-256 recorded

## Final report

- Artifacts inspected (paths)
- Structural validator result
- Content scan hits (fixed or justified)
- SHA-256 hashes
- Explicit confirmation: no private data in artifacts
