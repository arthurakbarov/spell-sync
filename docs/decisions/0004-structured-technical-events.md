# ADR 0004: Structured technical events

## Status

Accepted

## Context

Phase 4 split application services but operation progress still used free-form stage strings
(`OperationEvent.stage: str`) and the technical log mixed a few ad-hoc warning lines with
stdlib logging. There was no stable correlation between preview plan IDs, history record IDs,
and file log entries. CLI and TUI duplicated message wording at call sites.

Phase 5 must provide typed, privacy-safe technical events without changing Pull/Push semantics,
CLI JSON, exit codes, or mutation safety contracts.

## Decision

### 1. Typed event schema

Replace `OperationEvent` with frozen dataclasses and enums in `spell_sync/application/events.py`:

| Type | Role |
|------|------|
| `EventId` | Stable dotted identifiers (for example `push.plan_verified`) |
| `OperationKind` | Operation family (`pull`, `push`, `recover`, `setup`, `targets`, …) |
| `EventCategory` | `lifecycle`, `safety`, `target`, `transaction`, `recovery`, `diagnostic` |
| `EventSeverity` | `info`, `success`, `warning`, `error` |
| `EventPhase` | Optional lifecycle phase (`preparing`, `executing`, `rolling_back`, …) |
| `TechnicalEvent` | Canonical emission payload — no human message field |
| `PresentedEvent` | Human message produced only at presentation boundaries |

Optional typed metadata on `TechnicalEvent`:

| Field | Type |
|-------|------|
| `correlation_id` | `CorrelationId` |
| `target_id` | `TargetId` |
| `reason` | `EventReason` |
| `outcome` | `TerminalOutcome` |
| `completed`, `total` | non-negative integers with `completed <= total` when both set |

No arbitrary key/value bags. `EventLevel` remains a backward-compatible alias for
`EventSeverity`.

### 2. Stable event IDs

All lifecycle stages map to `EventId` enum members. Setup and target settings terminal
outcomes use dedicated IDs (`setup.failed`, `setup.stopped_safely`, `setup.incomplete`,
`targets.failed`, `targets.stopped_safely`). Application and core code emit known IDs only;
new stages require extending the enum and presenter map.

### 3. Presentation separation

- Application and focused services emit `TechnicalEvent` only.
- `spell_sync/application/event_presenter.py` maps `EventId` → user-facing copy in
  `PresentedEvent.message` (with small contextual overrides for `target_id` and typed
  `reason`).
- CLI and TUI pass a `PresentationEventSink` (`EventSink` alias) that receives
  `PresentedEvent`.
- The technical file log never stores presentation strings.

### 4. Correlation and target identifiers

`CorrelationId` and `TargetId` are validated opaque value types in
`spell_sync/application/event_metadata.py`:

- bounded ASCII-safe length;
- no path separators, whitespace, or control characters;
- correlation pattern: `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` with privacy deny substrings;
- target pattern: `^[a-z][a-z0-9_-]{0,63}$` with the same deny substrings.

Unsafe construction fails at the programming boundary; silent truncation or redaction of unsafe
input is not used.

### 5. JSON Lines logging (`schemaVersion` 1)

`spell_sync/diagnostics/technical_event_log.py` serializes each `TechnicalEvent` as one JSON
object per physical line (sorted keys, compact separators). Required fields:

```json
{
  "schemaVersion": 1,
  "timestamp": "2026-07-21T14:30:00Z",
  "eventId": "push.plan_verified",
  "operation": "push",
  "category": "lifecycle",
  "severity": "success"
}
```

Optional camelCase fields: `phase`, `correlationId`, `targetId`, `reasonCode`, `outcome`,
`completed`, `total`.

**Formatter contract:** records with `record.structured_event == True` are written as the exact
logger message (one JSON object) with no timestamp, level, logger name, or traceback prefix.
Legacy plain-text records keep the existing safe human-oriented formatter.

Only `write_technical_event()` may emit structured logger records.

### 6. Serializer validation

Serialization validates:

- exact allowed keys (`schemaVersion`, `timestamp`, `eventId`, `operation`, `category`,
  `severity`, optional metadata fields only);
- enum membership for all enum-backed fields;
- typed metadata values via `CorrelationId`, `TargetId`, `EventReason`, `TerminalOutcome`;
- non-negative counts and `completed <= total`.

Invalid events are rejected at serialize time. `write_technical_event()` suppresses serializer
failures (diagnostics-only fail-open) without writing raw unsafe values.

### 7. Fail-open boundaries

| Sink | Behavior |
|------|----------|
| Technical persistence (`write_technical_event`) | fail-open — serializer/handler errors suppressed |
| Presentation (`EventEmitter` → presentation sink) | programming exceptions propagate to caller |

TUI adapters may wrap presentation callbacks locally; `EventEmitter.emit()` must not swallow
presentation failures.

### 8. Canonical emission path

`operation_emitter(presentation_sink)` wires:

- `technical_sink` → `write_technical_event`
- `presentation_sink` → `present_event` → caller sink

Focused services create one `EventEmitter` per execution via `make_operation_emitter()` and
call `emit_technical(emitter, event)`. Setup and target settings pass `emitter.emit` to core
even when the presentation sink is `None`, so headless execution still writes technical events.

### 9. History and support integration

- Operation history remains compact user summaries via `history_store`.
- History append failure emits `diagnostics.history_write_failed` with typed `EventReason`.
- Support report does not embed raw technical log lines.
- Technical log tail uses `format_log_line_for_display` for concise summaries, not raw JSON.

### 10. Backward log reading

`parse_technical_log_line()` validates the full allowlisted schema and returns
`ParsedTechnicalLogEvent` or `None`. Legacy plain-text and malformed JSON lines fall back to
sanitized legacy display. Rotating backups may mix formats safely.

## Rejected alternatives

Network telemetry, OpenTelemetry envelopes, embedding presentation messages in technical events,
and storing the full event stream in operation history remain rejected (unchanged from Phase 5
draft).

## Consequences

### Positive

- One typed contract with validated metadata and terminal lifecycle coverage
- Real JSON Lines suitable for machine parsing
- Privacy constraints enforced at metadata construction and serialization
- Presentation failures remain observable

### Negative / constraints

- New lifecycle stages require enum, presenter, metadata, and architecture test updates
- Mixed legacy/structured log files until old rotations age out

## Compliance

Verified by focused technical-event, privacy, architecture, and safety suites; full CI evidence
recorded in `docs/ARCHITECTURE_0_3_IMPLEMENTATION.md` after Phase 5 corrective commits.
