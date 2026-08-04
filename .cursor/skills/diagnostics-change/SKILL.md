---
name: diagnostics-change
description: Change structured technical events, logging, history presentation, or support-report diagnostics with privacy and legacy compatibility checks.
---

# Diagnostics change

## When to use

- Adding or changing `EventId`, `TechnicalEvent`, or presenter copy
- Technical log serialization, tail display, or rotation behavior
- History append failure handling or support report diagnostic sections
- TUI Logs screen or operation progress event mapping

## Do not use

- Product Pull/Push semantics or dictionary write path changes (use `mutation-safety-audit`)
- Parallel event pipelines or free-form stage strings alongside typed events

## Required steps

1. **Event schema** — extend `EventId`, enums, and typed metadata in diagnostics modules; update presenter map.
2. **Lifecycle coverage** — emit terminal events for success, safe stop, and failure paths.
3. **Privacy review** — serialize-time forbidden keys; no user words, config bodies, or journal payloads.
4. **Legacy compatibility** — `parse_technical_log_line` and tail display must handle mixed JSON Lines and legacy text.
5. **Logs screen** — verify TUI tail rendering stays redacted for malformed lines.
6. **Support report** — confirm exports remain privacy-safe (no raw technical log dump).
7. **Failure handling** — technical log write remains fail-open; presentation errors propagate per existing policy.
8. **Adversarial privacy tests** — extend `tests/test_technical_logging.py` and `tests/test_diagnostic_redaction.py`.

## Validation

```bash
python3 scripts/run_dev_loop.py --cluster diagnostics-events --commit-gate
python3 -m pytest tests/tui/test_logs_screen.py -q
python3 scripts/check_architecture.py --check
python3 scripts/check_ci_necessity.py --purpose local --explain
```

Do not run full CI for ordinary diagnostics edits. L2 (`scripts/ci.sh` + `check_ci_evidence.py`)
only for `--purpose publish` / owner final.

Update `docs/architecture/DIAGNOSTICS.md` and ADR `docs/decisions/0004-structured-technical-events.md`
when contracts change.

## Related skills

- `mutation-safety-audit` — when diagnostics touch mutation paths
- `tui-flow` — Logs screen or operation progress UI
- `spell-sync-ci` — L2 publish CI and evidence

## Finalize workspace snapshot

Modifying tasks — after L1 (`run_dev_loop.py --commit-gate`). When L2 ran, require
`python3 scripts/check_ci_evidence.py` success first.
Skill `create-code-snapshot` in spell-sync-dev with `--force`, then `--check`;
canonical `$HOME/code.zip`; report §14 and footer `CODE_ARCHIVE` / `SHA256`.
SSOT: `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
