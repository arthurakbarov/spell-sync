---
name: preflight-publish
description: >-
  One gate before owner push or publish: clean tree, publish necessity, full CI,
  evidence, and privacy-export. Use when the owner asks to push, publish, or run
  publish preflight. Does not push, tag, or upload.
---

# Preflight publish

Shared contract: `.cursor/README.md` § Shared contract.

## When to use

- Owner asks to push, tag, release, publish, or "preflight publish"
- Final readiness check before any remote publish step

## Do not use

- After ordinary polish commits (use `run_dev_loop.py` / commit-gate)
- To push, tag, create GitHub Releases, or upload to PyPI without explicit owner request
- To skip privacy scan or CI evidence

## Loop (edit)

Not an edit loop. If the tree is dirty, stop and finish local work first:

```bash
python3 scripts/agent_context.py --purpose publish
python3 scripts/run_dev_loop.py --commit-gate
```

## Checkpoint

```bash
python3 scripts/preflight_publish.py
```

Prints readiness and the exact next commands. Does not run full CI unless `--execute`.

## Full gate (owner push / publish / final only)

```bash
python3 scripts/preflight_publish.py --execute
```

Sequence:

1. Clean working tree (no staged/unstaged/untracked tracked-path noise)
2. `python3 scripts/check_ci_necessity.py --purpose publish --explain`
3. `scripts/ci.sh` (direct; no `tail` / `tee`)
4. `python3 scripts/check_ci_evidence.py` (add `--release` when tagging/publishing)
5. Privacy checklist from skill `privacy-export` / `security-audit`

Stop before any `git push`, `gh release`, or package upload unless the owner explicitly
requested that remote step in the same message.

## Related

- Skill `spell-sync-ci` — local vs publish CI modes
- Skill `release-candidate` — version/artifacts after green preflight
- Skill `privacy-export` — public artifact scan
- Docs: `docs/ENGINEERING_COMPLETION.md`, `docs/INVENTORY.md`, `docs/CONTRACTS.md`
