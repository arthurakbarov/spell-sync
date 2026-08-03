# Getting Started

Spell Sync helps when **personal words you add in one app do not appear in another**.
It keeps those words in **one private word list** on your computer and lets you safely
copy them between supported applications.

You do **not** need Git, programming experience, or a special maintainer repository.

## What you need

- A Mac, Linux, or Windows computer
- Spell Sync installed (see [README](../README.md))
- A folder where you want to keep your personal word list

## Create your personal folder

Recommended layout:

```text
~/spell-words/
├── wordlist.txt
└── spell-sync.toml
```

You do **not** need to create these files by hand. The first run guides you.

### macOS or Linux

```bash
mkdir -p ~/spell-words
cd ~/spell-words
spell-sync
```

### Windows

Open PowerShell, create a folder, then run Spell Sync from that folder:

```powershell
mkdir $HOME\spell-words
cd $HOME\spell-words
spell-sync
```

## First safe steps

1. **Start Spell Sync** — with no arguments on a terminal it opens the UI.
2. **Set up a project** — choose a folder for your personal word list, or open an existing one.
3. **Check my apps** — see which applications were found and whether anything needs attention.
4. **Collect my words (Pull)** — preview words from your apps; confirm to add them to your list.
   Nothing is removed from your personal list during Collect.
5. Open `wordlist.txt` only if you want to read or edit words directly.
6. **Update my apps (Push)** — only after you understand the preview. Words missing from your
   personal list may be removed from **custom** dictionaries. Built-in dictionaries are never
   changed.

The guided setup does **not** run Update (Push) automatically.

### Same steps from the command line

If you prefer CLI (or have no interactive terminal):

| Goal | Command |
|------|---------|
| Non-interactive setup | `spell-sync init` |
| Collect words | `spell-sync pull` |
| Preview before update | `spell-sync status` or `spell-sync plan` |
| Update apps | `spell-sync push` |
| Check health | `spell-sync doctor` |
| Validate config | `spell-sync config-check` |

Full command list: [README → CLI](../README.md#cli).

## Optional: use a private Git repository

You may keep your personal folder in a **private** Git repository to sync between computers:

1. Copy the folder with your chosen private method (Git, backup drive, cloud folder).
2. Open Spell Sync on the second computer and point it at the same folder.
3. Run **Check my apps**, then preview **Update my apps** before confirming.

**Do not publish a personal word list unless you intend to share it.**

## If something goes wrong

See [Troubleshooting](TROUBLESHOOTING.md) and [Recovery](RECOVERY.md).

For supported applications, see [Supported Apps](SUPPORTED_APPS.md).

For where files live, see [Personal Workspace](PERSONAL_WORKSPACE.md).
