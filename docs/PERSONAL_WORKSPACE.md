# Personal Workspace

Your **personal workspace** is a folder **you** own. Spell Sync stores your word list and
configuration there. It is separate from the Spell Sync program itself.

## Recommended location

```text
~/Documents/Spell Sync/
```

Any writable folder works. Spell Sync does not require this exact path.

During first-time setup, the TUI asks **how** you will keep the list, then offers common
locations (Documents, Home, Desktop) or a custom path.

## What Spell Sync stores

| Item | Role |
|------|------|
| `wordlist.txt` | Your personal word list (you may edit this file) |
| `spell-sync.toml` | Which applications to sync (usually edited via the UI) |

Spell Sync may also create **application-managed** data (journals, locks, recovery snapshots)
next to your word list. You normally do not edit those by hand.

Because `spell-sync.toml` lives beside `wordlist.txt`, any method that syncs the folder also
syncs target choices. That is usually convenient; disable apps that do not exist on a given
machine under **Applications**.

## How to keep the list (choose one)

Spell Sync does **not** sync over the network by itself. Pick one approach:

| Approach | What you get | What to watch |
|----------|--------------|---------------|
| **This computer only** | Simplest. Folder stays on one machine. | Copy or move the folder yourself for backup or a second computer. |
| **Synced folder** (Dropbox, iCloud Drive, Yandex Disk, OneDrive, …) | The sync app copies the folder between machines — same outcome as a remote repo, without Git. | Pause sync if two computers might edit during a Push. Conflict copies from the sync app are outside Spell Sync. |
| **Private Git remote** (GitHub or any Git host) | You own a private copy of the same files on another machine. | Keep the repository **private**. After the word list changes, Status and Health warn if Git still has uncommitted `wordlist.txt` / `spell-sync.toml`. Commit with `spell-sync git-save` (add `--push` when an upstream exists). First-time repo creation remains a short setup step — see [`examples/init-personal-github-remote.sh`](examples/init-personal-github-remote.sh). |

Git is **optional**. Spell Sync works with a local folder alone.

Keep any Git remote private: a word list can reveal names and project terms.

## Moving later (change approach)

You can switch approaches without reinstalling Spell Sync:

1. Copy, move, or clone the folder to the new place (cloud folder or Git clone).
2. In Spell Sync, open **Change word list location** and point at the new `wordlist.txt`.
3. On another computer: open that same folder, then **Review and update** (or Check my apps,
   then preview Update).

Repoint does **not** move files — you move the folder yourself first.

## More than one computer

1. Keep the personal folder private through your chosen method (synced folder or Git).
2. Open Spell Sync on the other computer and select the same `wordlist.txt`.
3. Run **Check my apps**.
4. Preview **Update my apps** before confirming.

## Privacy

Your word list can reveal names, project terms, and personal vocabulary. Keep the folder and
any remote repository private. Do not publish a personal word list unless you intend to share it.
