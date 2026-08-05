# Artifacts and local state

What Spell Sync and maintainer tooling create on disk. Shareable vs local-only.
Git: [GIT-WORKFLOW.md](GIT-WORKFLOW.md). Snapshot procedure:
[AGENT_DEVELOPMENT.md](AGENT_DEVELOPMENT.md) § Workspace snapshot.

| Object | Purpose | Shareable | Typical path | When |
|--------|---------|-----------|--------------|------|
| CI evidence | Bound full-CI proof | no (local) | `.artifacts/` CI summaries | `scripts/ci.sh` |
| CI input digest | Necessity reuse key | no | under `.artifacts/` | CI / necessity scripts |
| Dead-code report | Tiny-module scan | no | `.artifacts/quality/dead-code-report.json` | `audit_dead_code.py` |
| Timing / execution history | ETA learning | no | execution-control SQLite (state dir) | budgeted / observe runs |
| Check-session ledger | Ephemeral reuse of successful checks in one agent arc | no | `/tmp/spell-sync-agent-session/` (override `SPELL_SYNC_CHECK_SESSION_DIR`) | `check_session.py` / `run_dev_loop.py` |
| Timeout diagnostics | Stall/hard captures | no | execution-control timeouts dir | hard/stall termination |
| Support report | Redacted user diagnostics | yes (export) | user-chosen path | `support-report` / TUI Health |
| Technical log | Operation JSONL | no | app state beside wordlist | product runs |
| Operation history | Compact outcomes | no | app state beside wordlist | product runs |
| Journal / snapshots | Push recovery | no | beside wordlist | interrupted Push |
| Project lock | Mutation exclusion | no | `.spell-sync.lock` near project | mutating ops |
| Workspace snapshot | Owner three-repo archive | optional | owner-home `code.zip` | modifying task end |
| Wheel / sdist | Release candidates | yes | `dist/` | packaging / RC |

## Rules

- Do not commit `.artifacts/` churn, `.venv/`, journals, or personal wordlists.
- Check-session state is ephemeral under `/tmp` (or `SPELL_SYNC_CHECK_SESSION_DIR`); never
  commit ledgers. Optional env: `SPELL_SYNC_CHECK_SESSION_ID`, `CURSOR_TRACE_ID`.
- SHA-256 for shareable archives belongs in reports / stdout — not sidecar files in
  the public tree.
- Product paths must not leak user words into technical logs or history
  ([architecture/DIAGNOSTICS.md](architecture/DIAGNOSTICS.md)).
- Maintainer snapshot policy lives in private `spell-sync-dev` (see [INVENTORY.md](INVENTORY.md)).

## Related

- Preflight: skill `preflight-publish`
- Privacy before share: skills `privacy-export` / `security-audit`
- Recovery product paths: [RECOVERY.md](RECOVERY.md)
