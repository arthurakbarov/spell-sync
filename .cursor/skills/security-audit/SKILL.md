---
name: security-audit
description: >-
  Audit spell-sync repo and artifacts for secrets, private paths, and unsafe
  patterns before commit, share, or push. Use before owner-requested push or
  when checking for confidential data leaks.
---

# Security audit (spell-sync)

Shared contract: `.cursor/README.md` § Shared contract.

## When to use

- Before any push the owner explicitly requests
- Before sharing wheels, sdists, or source archives
- When asked to check for confidential data or path leaks

## Do not use

- To archive a parent workspace or private wordlist repo
- As a substitute for mutation-safety product audits
- To push or publish

## Loop (edit)

Follow skill `privacy-export` checklist.

```bash
python3 scripts/check_agent_config.py
python3 scripts/scan_privacy_tree.py
python3 scripts/check_docs_contract.py
```

Optional (already covered by `scan_privacy_tree.py`):

```bash
rg -i 'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|github_pat_' .
```

## Checkpoint

- [ ] `privacy-export` checklist satisfied
- [ ] Agent config + docs contract green
- [ ] No secrets in `git diff --cached`

## Full gate (owner push / publish / final only)

From the **spell-sync-dev** maintainer workspace when the owner asked to publish
(`$SPELL_SYNC_DEV`, typically alongside this repo under `$HOME/code/`):

```bash
"$SPELL_SYNC_DEV/scripts/preflight-publish.sh"
python3 "$SPELL_SYNC_DEV/scripts/create-tool-evidence-archive.py" --force
```

## Related

Never commit personal wordlists, local `spell-sync.toml`, maintainer home paths, or
credentials.
