# ADR 0005: Secure internal artifact filesystem layer

## Status

Accepted (corrective work completed with phase-10)

## Context

Post-review security audit found that `.spell-sync.lock`, `.spell-sync.journal.json`, journal
temp files, and `.spell-sync.txn/` could follow symlinks or Windows reparse points (including
junctions), writing outside the trusted project root. Journal publication used a predictable temp
name and path-based writes without descriptor checks. Abort logic could discard recovery evidence
when journal update failed after an incomplete rollback. A process-global backup suppression flag
leaked across unrelated writes.

## Decision

### 1. Unified layer: `spell_sync/trusted_internal_fs.py` + `spell_sync/secure_artifacts.py`

All internal artifact open/create/publish/cleanup goes through descriptor/handle-relative
operations. Path strings are presentation-only after the trusted root is opened. Trust root is
the project directory from `ProjectContext` (wordlist parent), not `cwd`.

| Property | Behavior |
|----------|----------|
| Containment | POSIX: `dir_fd` traversal with `O_NOFOLLOW`/`O_DIRECTORY`; identity re-checked before final open |
| Same-user race | Parent directory swap between check and use fails closed via inode re-validation |
| Windows | Handle-based open with reparse inspection; path-based residual limitations documented |
| Modes | Private files `0600`, directories `0700` via `fchmod` on open descriptor |
| Hard links | Mutable lock files rejected when `st_nlink != 1` on POSIX |
| Cleanup | Enumerate via open directory fd; never `shutil.rmtree`; held fd prevents unrelated deletion |
| Snapshots | Exclusive create + copy on held destination fd; no pathname reopen for content |

### 2. Atomic journal publication

- Unique exclusive temp in the same trusted directory (not a fixed `.tmp` sibling name).
- Write all bytes → flush → file fsync (`FlushFileBuffers` best effort on Windows).
- Validate final path is a regular file or absent before `os.replace`.
- After replace: parent directory fsync on POSIX; documented best-effort on Windows.

**Guarantees (honest):**

| Guarantee | Scope |
|-----------|--------|
| Atomic visibility | Observers see old or new journal, not partial content |
| Process-crash safety | Prior journal preserved if publication fails before replace |
| Power-loss durability | Best effort via fsync; not proven by integration tests |
| Hostile root/administrator | Not in threat model; residual TOCTOU on Windows documented |

### 3. Abort precedence

Incomplete rollback **always** preserves journal and snapshots, regardless of journal update or
cleanup errors. Combined failures surface structured reasons with recovery materials flagged.

### 4. Explicit backup policy

Remove global `_BACKUP_DISABLED`. Transaction-owned dictionary writes pass
`keep_backup=False` to `atomic_write`; default writes keep rotating `.bak` behavior.

## Consequences

- New adversarial regressions in `tests/test_secure_artifacts_adversarial.py` (R1–R7),
  static guard in `tests/test_secure_artifacts_static_guard.py`, and existing mutation safety suites.
- Dictionary target paths remain product semantics (may follow app-configured paths); only
  spell-sync **internal** artifacts use this layer.
- Residual risk: same-user concurrent pathname replacement is mitigated on POSIX via held
  descriptors and inode re-validation; privileged attackers outside the supported threat model
  may still race on Windows where handle-relative cleanup is incomplete.

## References

- [MUTATION_SAFETY.md](../architecture/MUTATION_SAFETY.md)
- [RECOVERY.md](../RECOVERY.md)
- `spell_sync/trusted_internal_fs.py`
- `spell_sync/secure_artifacts.py`
