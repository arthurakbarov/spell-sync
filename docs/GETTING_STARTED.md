# Getting Started

## The problem

You add a personal word in one place — a name, product term, or abbreviation in a
browser or editor. Later another app underlines it as a mistake. You fix it again.
The list of "words only I care about" is scattered across apps and never stays in sync.

## What Spell Sync does

Spell Sync keeps **one private word list** on your computer and helps you:

1. **Collect** personal words already stored in apps into that list.
2. **Update** those apps so they match your list.

You always see a **preview** and confirm before anything changes. Spell Sync only
touches each app's **custom** word list — never the built-in dictionary that ships
with the app.

You do **not** need Git, programming experience, or a special maintainer repository.
Git and cloud sync folders are **optional** ways to keep the same list on more than one
computer — see [Personal Workspace](PERSONAL_WORKSPACE.md).

## What you need

- A Mac, Linux, or Windows computer
- **Python 3.11+** and Spell Sync installed ([README → Install](../README.md#install);
  `uv` recommended, `pip` also works; no PyPI package yet)
- An empty folder for your private word list (Spell Sync creates the files). Where that
  folder lives is your storage choice: this computer only, a synced cloud folder, or a
  private Git remote.

## Fastest path (terminal UI)

This is the usual non-technical path.

### 1. Open a folder and start Spell Sync

**macOS or Linux**

```bash
mkdir -p ~/Documents/Spell\ Sync
cd ~/Documents/Spell\ Sync
spell-sync
```

**Windows (PowerShell)**

```powershell
mkdir $HOME\Documents\Spell Sync
cd $HOME\Documents\Spell Sync
spell-sync
```

If you already use Dropbox, iCloud Drive, or Yandex Disk, create the folder **inside**
that synced area instead (for example `~/Library/CloudStorage/…` or your Dropbox path).

### 2. First launch — Start here

On the welcome screen:

1. Read the short problem summary.
2. Press **Start here**.
3. Answer **How will you keep this word list?** (this computer / synced folder / private Git).
4. Accept or choose the folder for your word list.
5. Pick which apps to include (you can change this later under **Targets**).
6. Confirm setup.

You do not need to create `wordlist.txt` by hand.

### 3. Day to day — one primary action

On the dashboard, use **Review and update** (the main button).

It walks you through:

1. Collect new words from your apps → preview → confirm if you want them.
2. Update your apps from your list → preview → confirm if you want the update.

That is the "two-step with previews" path. Separate Collect / Update buttons exist if you
only want one direction.

Setup never runs Update automatically.

## Optional: command line

If you prefer commands (or have no interactive terminal):

| Goal | Command |
|------|---------|
| Non-interactive setup | `spell-sync init` |
| Collect my words | `spell-sync pull` |
| Preview before update | `spell-sync status` or `spell-sync plan` |
| Update my apps | `spell-sync push` |
| Check health | `spell-sync doctor` |

Full list: [README → CLI](../README.md#cli).

After `init`, read [Personal Workspace](PERSONAL_WORKSPACE.md) if you want the same list on
another computer (synced folder or private Git).

## Optional: second computer

Spell Sync does not sync over the network by itself. Choose one private method:

| Method | Idea |
|--------|------|
| Synced folder | Keep the folder in Dropbox / iCloud / Yandex Disk / … on both machines |
| Private Git | Clone your private repo on each machine ([Personal Git remote](PERSONAL_GIT_REMOTE.md)) |
| Manual copy | Copy the folder on a drive when needed |

On the other computer open the same folder in Spell Sync, then **Review and update**
(or Check my apps and preview Update).

To switch methods later: move or clone the folder, then **Change word list location**.

**Do not publish a personal word list unless you intend to share it.**

## If something goes wrong

See [Troubleshooting](TROUBLESHOOTING.md) and [Recovery](RECOVERY.md).

Supported applications: [Supported Apps](SUPPORTED_APPS.md).  
Where files live: [Personal Workspace](PERSONAL_WORKSPACE.md).
