---
name: git-change-management
description: >-
  Git branch, index, commit, stash, and push workflow for agents on spell-sync.
  Use before staging, committing, or when clarifying git policy. Local commits
  do not need owner approval; push/tag/publish do.
---

# Git change management (spell-sync)

Shared contract: `.cursor/README.md` § Shared contract (note intentional divergence
from nix: local commits anytime here).

Rule: `.cursor/rules/git-change-management.mdc`.

## When to use

- Before staging or committing
- When clarifying push / stash / branch policy
- During modifying work that needs local checkpoints

## Do not use

- To push, tag, or publish without an explicit owner request
- To force-push `main` / `master`
- To rewrite history unless the owner explicitly asks

## Loop (edit) — allowed without owner approval

- `python3 scripts/agent_context.py` (optional `--json`) before staging
- `git status`, `git diff`, `git log`, `git branch`, `git show`
- `git add`, `git commit` on **any** local branch (including `main`), anytime
- Local WIP / checkpoint commits; prefer commits over persistent `git stash`
- Creating/switching local feature branches

## Checkpoint

Before declaring a commit boundary / task done:

```bash
python3 scripts/run_dev_loop.py --commit-gate
```

Mid-arc micro-checkpoints may use the edit loop alone.

### Commit message shape

- One concern per commit
- Imperative subject ending with `.` (no `feat:` / `docs:` / `Wave E:` prefixes)
- Optional short why-body; fold tracker/evidence notes into the producing commit

## Full gate (owner push / publish / final only)

Owner approval required:

- `git push`, tags, GitHub Release, package publish
- Force-push, `git reset --hard`, `git clean -fd`, history rewrite

## Related

- Skill `repository-workflow` — full change arc
- Skill `security-audit` — privacy before share/push
- Skill `privacy-export` — public artifact scan
