# Diagnostics

Spell Sync separates **presentation** (what CLI/TUI show), **technical events** (structured
operation trace), **operation history** (compact user summaries), and **support reports**
(redacted export).

## Distinction

| Sink | Content | User words | Format |
|------|---------|------------|--------|
| UI events (`PresentedEvent`) | Progress and outcome copy | Never in payloads | Human strings at CLI/TUI |
| Technical events (`TechnicalEvent`) | Operation trace | Forbidden at serialize time | JSON Lines (`schemaVersion: 1`) |
| Operation history | Last operations summary | Never | Compact store |
| Support report | Diagnostics bundle | Redacted | Export file / JSON |

## Technical event schema

Canonical types live in `spell_sync/diagnostics/technical_event_model.py` and
`spell_sync/application/events.py`:

| Field | Role |
|-------|------|
| `EventId` | Stable dotted identifier (`push.plan_verified`, …) |
| `OperationKind` | `pull`, `push`, `recover`, `setup`, `targets`, … |
| `EventCategory` | `lifecycle`, `safety`, `target`, `transaction`, … |
| `EventSeverity` | `info`, `success`, `warning`, `error` |
| `EventPhase` | Optional phase (`preparing`, `executing`, …) |
| `correlationId` | Binds preview plan IDs, setup/update IDs, history IDs |
| `targetId` | Optional per-target scope |
| `reasonCode` / `outcome` | Typed terminal metadata |

Serialization allowlist and privacy rules: `spell_sync/diagnostics/technical_event_log.py`.

See ADR [0004-structured-technical-events.md](../decisions/0004-structured-technical-events.md).

## Emission path

```text
service / core helper
  → emit_technical / operation_emitter
  → write_technical_event (JSON Lines file log, fail-open)
  → present_event → PresentedEvent → CLI/TUI EventSink
```

Only `write_technical_event()` writes structured logger records. Legacy plain-text lines remain
supported for tail display via sanitization.

## Correlation lifecycle

1. Preview assigns a plan or update identifier.
2. Technical events for that operation reuse `correlationId`.
3. History append failures emit `diagnostics.history_write_failed` with typed reason.
4. Logging setup failures emit `diagnostics.logging_setup_failed` — never block mutation.

## Privacy

- Serialize-time forbidden keys reject user dictionary content.
- No raw config, credentials, journal bodies, or HOME paths in events.
- Malformed JSON-like tail lines are redacted in display.
- Support report does not embed raw technical log payloads.

Tests: `tests/test_technical_logging.py`, `tests/test_diagnostic_redaction.py`.

## Failure behavior

| Failure | Effect |
|---------|--------|
| Technical log write | Suppressed (fail-open) — Pull/Push/Recovery continue; optional `SPELL_SYNC_DEBUG` traceback on stderr |
| Presentation callback | Fail-open — product path continues; static `diagnostics.presentation_sink_failed` may be written to the technical log only (never re-entered through the failing presentation sink) |
| History append | Recorded via diagnostic event; operation outcome unchanged |

## Developer debug (`SPELL_SYNC_DEBUG`)

Opt-in maintainer/developer diagnostics. **Not** a normal user-facing setting.

| Rule | Detail |
|------|--------|
| Enable | `SPELL_SYNC_DEBUG=1` (also `true` / `yes` / `on`) |
| Default | Off |
| Output | Tracebacks go **only** to `stderr` |
| Contracts | stdout and JSON CLI payloads are unchanged |
| Privacy | Exception messages may include local paths or other sensitive details — do **not** attach raw debug output to public issues or support reports without review |

Unexpected boundary failures may also emit low-cardinality technical events such as
`diagnostics.doctor_unexpected_failure` and `diagnostics.tui_launch_unexpected_failure`
(no exception message or traceback in the event payload).

## Rotation and legacy parsing

Rotating technical log files may mix JSON Lines and legacy plain-text records.
`parse_technical_log_line()` validates structured lines; legacy lines use
`sanitize_log_message` for display.

## Adding a new event

1. Add `EventId` enum member and presenter copy in `event_presenter.py`.
2. Emit through `operation_emitter` / `emit_technical` only.
3. Extend privacy tests if new metadata fields are introduced.
4. Run architecture and diagnostics test clusters.

Do not add free-form stage strings or parallel logging pipelines.

## Tests required for new operation stages

- Event emission on happy path and terminal outcomes
- Privacy redaction on log tail and support paths
- TUI progress mapping from `EventId` when user-visible
- Pull/Push/Recovery safety suites when mutation paths change
