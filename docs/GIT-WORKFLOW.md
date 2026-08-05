# Git workflow (SSOT)

Single source of truth for branch, index, commit, stash, rollback, and push policy in
this spell-sync repository.

Related: [`AGENTS.md`](../AGENTS.md), [`.cursor/rules/git-change-management.mdc`](../.cursor/rules/git-change-management.mdc),
skill `git-change-management`, [`docs/AGENT_DEVELOPMENT.md`](AGENT_DEVELOPMENT.md).

Shared **commit message shape** with nix-darwin (`docs/GIT-WORKFLOW.md` there). Branch and
commit-authorization rules diverge intentionally (see **Project note** below).

## Roles

| Role | Git authority |
|------|----------------|
| Repository owner | Approves push, tag, release, publish, and destructive history recovery |
| Cursor Agent | Local commits anytime on any branch; push/tag/publish only when owner asks |

Inspect current state: `python3 scripts/agent_context.py` (optional `--json`) then `git status`.

## Branch policy

### Default branch (`main`)

- Local commits on `main` are **allowed** (checkpoints, WIP, completed chunks).
- Never force-push `main` without an explicit owner request in the current arc.

### Feature branches

- Name: `type/short-topic` when splitting work (examples: `feat/writer-goldens`,
  `fix/recovery-digest`).
- Prefer one coherent arc per branch; use WIP commits instead of long-lived stash.

### Rescue branch

Create a rescue branch before risky history edits:

```bash
git branch rescue/$(date +%Y%m%d)-<topic>
```

Rescue branches are snapshots, not long-lived integration branches. Push them only when
the owner asks.

## Index policy

- Stage **coherent slices** (one concern per commit).
- Never stage personal wordlists, local `spell-sync.toml`, credentials, or maintainer home
  paths.
- Unstage with `git restore --staged <path>` (not `git reset --hard`).

## Commit policy

### When commits happen

- Agents **may and should** create local commits on any local branch without waiting for
  operator approval.
- Prefer small coherent commits after validation (`run_dev_loop.py` / `--commit-gate`).
- Do not hide unfinished work in persistent `git stash`.

### Commit splitting

One concern per commit:

| Concern | Examples |
|---------|----------|
| Product / mutation | Pull, Push, Recovery, writers, application services |
| Tooling / CI | execution control, impact registries, runners |
| Agent-config | `.cursor/rules`, skills, agent contracts |
| Docs-only | public docs without code |

Fold into the producing commit (do **not** land as separate tip commits):

- Ruff / format / unused-import follow-ups from the same change
- Tracker “record tip HEAD / CI evidence” notes for that change
- Empty “sync tracker to tip” commits

Use `git commit --fixup=<target>` on a feature branch during review; autosquash only when
the owner explicitly asks.

### Commit message shape (shared with nix-darwin)

- Subject: imperative mood, present tense, about 50–72 chars, **ends with `.`**
- Blank line between subject and body when a body is present
- Subject says **why** / user-visible outcome — not a file list
- Optional body: 1–3 lines of why/context; no bullet dumps of paths
- Do **not** use Conventional Commit type prefixes (`feat:`, `fix:`, `docs:`)
- Do **not** use wave/phase labels in the subject (`Wave E:`, `Phase 10:`)

Example:

```
Harden mutation safety and close coverage-policy CI gaps.

Missing targets must prove continued absence; Recovery confirmations bind to
journal content digests under lock.
```

Validate recent history:

```bash
python3 scripts/validate_commit_messages.py
```

Optional local `commit-msg` hook (this repository only; opt-in):

```bash
python3 scripts/install_git_hooks.py install
python3 scripts/install_git_hooks.py status
python3 scripts/install_git_hooks.py remove
```

Use `--force` only to replace an unmanaged hook. Product doctor `install-hooks`
actions still refer to wordlist-repository hooks, not this installer.

### Pre-commit checklist

1. `python3 scripts/agent_context.py` then `git status` / `git diff`.
2. Validation for the boundary (edit loop or `--commit-gate`).
3. Subject + optional why-body per **Commit message shape**.

## Stash policy

- Prefer named branches + normal WIP commits over long-lived stashes.
- Stash only for brief context switches; name with `git stash push -m "wip: <topic>"`.
- Final task state: `git stash list` must be empty in this repository.

## Rollback (Git)

| Situation | Safe action |
|-----------|-------------|
| Unstage file | `git restore --staged <path>` |
| Discard unstaged edits | `git restore <path>` (owner approval for broad discard) |
| Undo last commit, keep changes | `git reset --soft HEAD~1` (owner approval when rewriting shared tip) |
| Abandon commit on shared remote | `git revert <sha>`; avoid `reset --hard` without rescue branch |

**Forbidden without explicit owner request:** `git reset --hard`, `git clean -fd(x)`,
force-push, `git filter-repo` / history rewrite, any `git push`, tag, release, or publish.

## Push prohibition

- Agents must not push unless the owner explicitly asks in the current arc.
- Never force-push `main` / `master` without an explicit owner request.
- Before owner-authorized push: commit-gate, `check_ci_necessity.py --purpose publish`,
  full `scripts/ci.sh` when required, then `check_ci_evidence.py`.

## Project note (vs nix-darwin)

| Topic | spell-sync | nix-darwin |
|-------|------------|------------|
| Commit message shape | Same (imperative + trailing `.`) | Same |
| Local commits on `main` | Allowed anytime | Forbidden for agents |
| Commit without ask | Allowed | Feature branch + explicit ask |
| Push / force-push / tag | Owner-gated | Owner-gated |
