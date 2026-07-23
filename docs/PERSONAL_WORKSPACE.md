# Personal Workspace

Your **personal workspace** is a folder **you** own. Spell Sync stores your word list and
configuration there. It is separate from the Spell Sync program itself.

## Recommended location

```text
~/spell-words/
```

Any writable folder works. Spell Sync does not require this exact path.

## What Spell Sync stores

| Item | Role |
|------|------|
| `wordlist.txt` | Your personal word list (you may edit this file) |
| `spell-sync.toml` | Which applications to sync (usually edited via the UI) |

Spell Sync may also create **application-managed** data (journals, locks, recovery snapshots)
next to your word list. You normally do not edit those by hand.

## Backup options

- Copy the folder to a backup drive
- Keep it in a **private** Git repository
- Sync via a private cloud folder

Git is **optional**. Spell Sync works without version control.

## More than one computer

1. Sync the personal folder through your chosen private method.
2. Open Spell Sync on the other computer.
3. Run **Check my apps**.
4. Preview **Update my apps** before confirming.

Spell Sync does not provide automatic network sync between computers.

## Privacy

Your word list can reveal names, project terms, and personal vocabulary. Keep the folder private.
