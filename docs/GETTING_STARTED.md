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

## What you need

- A Mac, Linux, or Windows computer
- Spell Sync installed ([README → Install](../README.md#install))
- An empty folder for your private word list (Spell Sync creates the files)

## Fastest path (terminal UI)

This is the usual non-technical path.

### 1. Open a folder and start Spell Sync

**macOS or Linux**

```bash
mkdir -p ~/spell-words
cd ~/spell-words
spell-sync
```

**Windows (PowerShell)**

```powershell
mkdir $HOME\spell-words
cd $HOME\spell-words
spell-sync
```

### 2. First launch — Start here

On the welcome screen:

1. Read the short problem summary.
2. Press **Start here**.
3. Accept or choose the folder for your word list.
4. Pick which apps to include (you can change this later under **Targets**).
5. Confirm setup.

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
| Collect words | `spell-sync pull` |
| Preview before update | `spell-sync status` or `spell-sync plan` |
| Update apps | `spell-sync push` |
| Check health | `spell-sync doctor` |

Full list: [README → CLI](../README.md#cli).

## Optional: second computer

Keep your personal folder private (backup drive, private Git, private cloud). On the other
computer open the same folder in Spell Sync, then **Review and update** (or Check my apps
and preview Update). Spell Sync does not sync over the network by itself.

**Do not publish a personal word list unless you intend to share it.**

## If something goes wrong

See [Troubleshooting](TROUBLESHOOTING.md) and [Recovery](RECOVERY.md).

Supported applications: [Supported Apps](SUPPORTED_APPS.md).  
Where files live: [Personal Workspace](PERSONAL_WORKSPACE.md).
