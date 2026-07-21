# ADR 0004: Structured technical events

## Status

Accepted (Phase 5 awaiting owner approval)

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

Optional fields on `TechnicalEvent`: `correlation_id`, `target_id`, `reason_code`, `outcome`,
`completed`, `total`. No arbitrary key/value bags.

`EventLevel` remains a backward-compatible alias for `EventSeverity`.

### 2. Stable event IDs

All lifecycle stages map to `EventId` enum members. Application and core code emit known IDs
only; new stages require extending the enum and presenter map. Architecture tests forbid
reintroducing free-form stage strings on the canonical path.

### 3. Presentation separation

- Application and focused services emit `TechnicalEvent` only.
- `spell_sync/application/event_presenter.py` maps `EventId` → user-facing copy in
  `PresentedEvent.message` (with small contextual overrides for `target_id` and `reason_code`).
- CLI and TUI pass a `PresentationEventSink` (`EventSink` alias) that receives `PresentedEvent`.
- The technical file log never stores presentation strings.

### 4. Correlation IDs

`correlation_id` ties events within one operation attempt:

- Pull/Push execution: preview `plan_identifier`
- Setup: prepared setup identifier
- Target settings: update identifier
- Recovery: recovery preview identifier
- Diagnostics failures: history `record_id` when history append fails

Correlation IDs appear in JSON Lines output as `correlationId`. They are opaque identifiers,
not wordlist or config content.

### 5. JSON Lines logging (`schemaVersion` 1)

`spell_sync/diagnostics/technical_event_log.py` serializes each `TechnicalEvent` as one JSON
object per line (sorted keys, compact separators). Required fields:

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

Structured lines are written through the existing rotating file handler with
`extra={"structured_event": True}` so `safe_log` bypasses message sanitization on the JSON
payload itself (sanitization still applies to legacy plain-text lines).

### 6. History and support integration

- **Operation history** remains compact user summaries via `history_store` and
  `build_history_record` — events do not duplicate word counts or target diffs into history.
- When history append fails, `DiagnosticsService.finalize_report` emits
  `diagnostics.history_write_failed` with `correlation_id=record_id` and adds the existing
  user warning to the report.
- **Support report** continues to expose redacted operation summaries (`recent_operations`) and
  privacy manifest; it does not embed raw technical log lines or event payloads.
- **Technical log tail** (dashboard, diagnostics UI) uses `format_log_line_for_display` to show
  concise `severity eventId [target=…]` summaries for structured lines.

### 7. Privacy allowlist

Technical events use an explicit field allowlist at serialization time. Forbidden payload keys
(for example `words`, `wordlist`, `raw_config`, `path`, `message`, `environment`,
`journal_payload`) raise at serialize time if present. Presentation copy is fixed strings in
`event_presenter.py`, not user data. Existing `safe_log` redaction remains for non-structured
log records.

### 8. Fail-open diagnostics

`EventEmitter.emit` wraps both technical and presentation sinks in try/except and ignores
failures. Logging setup failure emits `diagnostics.logging_setup_failed` when possible but
never blocks service construction or mutation paths. Pull/Push/Recovery semantics are unchanged
if the log file is missing or unwritable.

### 9. Backward log reading

`parse_technical_log_line` accepts only JSON objects with `schemaVersion: 1` and a known
`eventId`. Legacy plain-text lines return `None` from the parser; display falls back to
`sanitize_log_message` on the raw line. Rotating backups may therefore mix old and new formats
safely.

### 10. Canonical emission path

`operation_emitter(presentation_sink)` wires:

- `technical_sink` → `write_technical_event`
- `presentation_sink` → `present_event` → caller sink

Focused services call `emit_technical` from `_shared.py`. There is no parallel legacy
`OperationEvent` pipeline after migration.

## Rejected alternatives

### Network telemetry / remote logging

Deferred. Structured events are local-only (rotating file under app state). No batching,
upload, or third-party analytics SDK. Rationale: privacy, offline use, and mutation-path
simplicity.

### OpenTelemetry / generic observability envelope

Rejected for 0.3. Spell Sync needs a small, privacy-reviewed schema tied to operation IDs and
support workflows, not a general tracing product. Correlation IDs are operation-scoped, not
distributed trace spans.

### Embedding presentation messages in technical events

Rejected. Human copy belongs in `event_presenter.py` only so CLI/TUI/TUI tests can evolve
wording without changing log parsing or support contracts.

### Storing full event stream in operation history

Rejected. History stays user-oriented summaries; the technical log holds the structured
lifecycle trail.

## Consequences

### Positive

- One typed contract for Pull/Push/Recovery/setup/targets progress
- Technical log lines are machine-parseable with stable IDs
- Correlation IDs link preview, execution events, and history diagnostics
- Presentation boundaries stay in CLI/TUI adapters and `event_presenter.py`
- Privacy constraints are enforceable at serialize time

### Negative / constraints

- New lifecycle stages require enum + presenter + tests updates
- Mixed legacy/structured log files until old rotations age out
- Event coverage tests must stay aligned with enum growth

## Compliance

Verified by (pending final CI on Phase 5 HEAD):

- `tests/test_technical_logging.py`, `tests/test_diagnostic_redaction.py`
- Pull/Push/Recovery safety and TUI architecture suites (unchanged semantics)
- privacy redaction tests on `safe_log` and technical tail display
- full CI on committed clean HEAD (pending owner approval)
