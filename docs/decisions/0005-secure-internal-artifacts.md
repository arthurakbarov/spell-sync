# ADR 0005: Secure internal artifact filesystem layer

## Status

Accepted (corrective work, phase-10 awaiting approval)

## Context

Post-review security audit found that `.spell-sync.lock`, `.spell-sync.journal.json`, journal
temp files, and `.spell-sync.txn/` could follow symlinks or Windows reparse points (including
junctions), writing outside the trusted project root. Journal publication used a predictable temp
name and path-based writes without descriptor checks. Abort logic could discard recovery evidence
when journal update failed after an incomplete rollback. A process-global backup suppression flag
leaked across unrelated writes.

## Decision

### 1. Unified layer: `spell_sync/secure_artifacts.py`

All internal artifact open/create/publish/cleanup goes through one module. Trust root is the
project directory from `ProjectContext` (wordlist parent), not `cwd`.

| Property | Behavior |
|----------|----------|
| Containment | Child paths verified under trusted root; existing link/reparse components rejected fail-closed |
| POSIX open | `O_NOFOLLOW` where available; post-open `fstat` must show regular file or expected directory |
| Windows | Reject `FILE_ATTRIBUTE_REPARSE_POINT` on existing components (symlinks and junctions) |
| Modes | Private files `0600`, directories `0700` via descriptor-based chmod where possible |
| Cleanup | Remove only operation-owned paths; never follow links; preserve evidence on doubt |

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

- New adversarial and fault-matrix tests in `tests/test_internal_artifact_security.py`,
  `tests/test_secure_artifacts.py`, and existing mutation safety suites.
- Dictionary target paths remain product semantics (may follow app-configured paths); only
  spell-sync **internal** artifacts use this layer.
- Residual risk: concurrent privileged attacker replacing path components between check and open
  is mitigated on POSIX via descriptor-relative patterns where used, but not eliminated on all
  platforms.

## References

- [MUTATION_SAFETY.md](../architecture/MUTATION_SAFETY.md)
- [RECOVERY.md](../RECOVERY.md)
- `spell_sync/secure_artifacts.py`
