# Personal Git remote (optional)

Use this only if you chose **Private Git remote** during setup (or later moved your folder
into a Git repository). Spell Sync does not create remotes, commit, or push for you.

Any Git host works. The steps below are ready-to-run for **GitHub** with the
[`gh`](https://cli.github.com/) CLI. Adapt the remote URL for GitLab, Codeberg, Forgejo, or
a self-hosted server.

## Before you start

- Keep the repository **private**. A word list can reveal names and project terms.
- Put only your personal workspace in the repo (`wordlist.txt`, `spell-sync.toml`, and
  Spell Sync state next to them) — not the Spell Sync program source.
- Install Git. For the GitHub recipe, install and authenticate `gh` (`gh auth login`).

## Create a private GitHub repo from an existing folder

From the folder that already contains `wordlist.txt` (example path):

```bash
cd "$HOME/Documents/Spell Sync"
git init
git add wordlist.txt spell-sync.toml
# Optional: ignore local churn you do not want shared
# printf '%s\n' '.DS_Store' >> .gitignore && git add .gitignore
git commit -m "Add personal Spell Sync word list"
gh repo create spell-sync-words --private --source=. --remote=origin --push
```

Or run the helper script from a Spell Sync source checkout:

```bash
bash docs/examples/init-personal-github-remote.sh "$HOME/Documents/Spell Sync"
```

## Second computer

```bash
gh repo clone <you>/spell-sync-words "$HOME/Documents/Spell Sync"
cd "$HOME/Documents/Spell Sync"
spell-sync
```

Choose **Open existing word list** and select `wordlist.txt`. Then **Review and update**.

## Day to day

After editing the list (in Spell Sync or by hand):

```bash
cd "$HOME/Documents/Spell Sync"
git add wordlist.txt spell-sync.toml
git commit -m "Update personal word list"
git push
```

On the other machine: `git pull`, then open Spell Sync and Review and update.

## Switch away from Git later

1. Copy the folder out of the clone into a normal or cloud-synced path if you want.
2. Use **Change word list location** in Spell Sync to point at the new `wordlist.txt`.
3. You may delete the old clone when you no longer need it.

See [Personal Workspace](PERSONAL_WORKSPACE.md) for the full storage fork (local / cloud / Git).
