# Operations

Runbooks for common Spell Sync failure modes. State vocabulary:
[CONTRACTS.md](CONTRACTS.md). Symptom index: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
Recovery product detail: [RECOVERY.md](RECOVERY.md).

Normal recovery favors read-only diagnostics, targeted fixes, and explicit confirm.
Destructive actions are marked and are not default steps.

---

## Command not found after install

### Symptoms

- Shell cannot find `spell-sync` after `uv tool install` or `pip install`.

### Safe diagnostics

```bash
python3 -m spell_sync version
which spell-sync || true
```

### Expected states

- **installed**: package present in the environment used for install.
- **ready**: `spell-sync` on `PATH`, or `python3 -m spell_sync` works.

### Recovery

1. Re-open the terminal; run `uv tool update-shell` if you used uv.
2. Ensure the user scripts directory is on `PATH`.
3. Prefer `python3 -m spell_sync` until PATH is fixed.

### Destructive actions

- None required.

Full copy: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#spell-sync-was-installed-but-the-command-is-not-found).

---

## Invalid configuration blocks writes

### Symptoms

- Mutating commands refuse to run; TUI shows blocked / invalid config.

### Safe diagnostics

```bash
spell-sync config-check
spell-sync doctor
spell-sync status --json
```

### Expected states

- **configured**: `config-check` accepts `spell-sync.toml`.
- **blocked**: invalid config or unreadable wordlist until fixed.

### Recovery

1. Fix diagnostics from `config-check` / doctor checks.
2. Re-run `doctor` until blocking errors are gone.
3. Rebuild preview before Pull/Push — do not reuse a stale plan.

### Destructive actions

- Do not delete the wordlist to "fix" config.

---

## Pending Recovery blocks new writes

### Symptoms

- Dashboard blocked; Pull/Push refuse; doctor or status mentions recovery.

### Safe diagnostics

```bash
spell-sync recover --help
spell-sync doctor --json
```

### Expected states

- **blocked** while a valid in-progress journal exists.
- **ready** after successful recover (journal artifacts removed).

### Recovery

1. Run TUI **Review recovery** or `spell-sync recover`.
2. Prefer restore paths over discard.
3. Only use `--discard-corrupt-journal` deliberately on corrupt journals.

### Destructive actions

- Discarding a corrupt journal throws away recovery snapshots for that transaction.

Detail: [RECOVERY.md](RECOVERY.md).

---

## Push skipped because an app is running

### Symptoms

- Preview or Push skips Chrome/Firefox/Obsidian (or similar) while the app is open.

### Safe diagnostics

```bash
spell-sync doctor --targets
spell-sync plan --json
```

### Expected states

- **discovered** / **readable** for the target; Push may still be skipped for close policy.
- After close + fresh plan: Push can become **executable**.

### Recovery

1. Quit the application completely.
2. Rebuild Push preview (stale plan must not run).
3. Confirm and Push again.

### Destructive actions

- None. Do not force-kill unless the user chooses to.

---

## Stale preview / plan mismatch

### Symptoms

- Confirm fails because plan ID or fingerprint no longer matches.

### Safe diagnostics

- Re-run preview (`plan` / TUI Review and update). Compare that confirmation binds to the
  new plan only.

### Expected states

- **planned** then **executed** for one immutable prepared object.
- False equivalence banned: plan preview ≠ executed ([CONTRACTS.md](CONTRACTS.md)).

### Recovery

1. Discard the stale confirmation UI.
2. Build a fresh preview.
3. Confirm the new plan only.

### Destructive actions

- None.

---

## Escalation

1. Export `spell-sync support-report` (redacted).
2. Check [FEATURE_MATRIX.md](FEATURE_MATRIX.md) before claiming a target "works".
3. Maintainer: `python3 scripts/dev_runs.py failures` for harness failures — not product
   Pull/Push logs.
