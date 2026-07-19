# Spell Sync 0.2.1 transparency implementation

## Goal

Make target capabilities, platform limits, and operation outcomes machine-readable,
user-visible, and agent-verifiable without changing Pull/Push/Recovery architecture.

## Verified baseline

- Version: `0.2.0`
- HEAD: `abc8916` (fix: harden agent configuration validation)
- Working tree clean; agent config validator OK; full CI green
- Existing: TUI, targets management, Review workflow, UserNotice, planned/actual reports

## Existing target metadata

| Source | Contents |
|--------|----------|
| `project_setup/discovery.py` | `_CONFIG_TARGET_IDS`, `_DISPLAY_NAMES`, `SetupTarget` runtime state |
| `dictionaries.py` | `Dictionary`, formats, subset fns, discovery per app |
| `app_process_check.py` | Running-app skip rules (chrome, edge, firefox, obsidian) |
| `application/product_concepts.py` | User-facing Pull/Push/filtering copy |

Duplication today: display names, OS support, subset mapping, close policy spread across
discovery, dictionaries, and docs.

## Existing diagnostic model

- `diagnostics/paths.py` — app state directory (history, technical log)
- `health/report.py` — doctor checks
- `application/builders.py` — dashboard, doctor, operation reports
- No support report or session export yet

## Safety invariants

Unchanged: lock, immutable previews, fingerprint, Recovery blocks, no user words in logs/history,
TUI via service facade, no auto Pull/Push.

## Current phase

Phase 1 — target capability registry

## Completed phases

(none yet)

## Last validation

(pending)

## Remaining work

Phases 1–8 per release plan.

## Deferred work

TargetAdapter refactor, profile editor, GUI, watcher, cloud sync, built-in dictionary inspection.
