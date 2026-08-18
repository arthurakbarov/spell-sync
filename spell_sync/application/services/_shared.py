"""Shared helpers for application services."""

from ...runtime_identity import RuntimeIdentity
from ..events import EventEmitter, PresentationEventSink, TechnicalEvent, operation_emitter

HISTORY_SAVE_WARNING = "Operation completed, but its history record could not be saved."

RUNTIME_CHANGED_MESSAGE = (
    "Project configuration or targets changed after the preview was created. "
    "Request a new preview before executing."
)


def make_operation_emitter(presentation_sink: PresentationEventSink | None) -> EventEmitter:
    return operation_emitter(presentation_sink)


def emit_technical(emitter: EventEmitter, event: TechnicalEvent) -> None:
    emitter.emit(event)


def running_app_skip_reasons_for(settings):
    from ...app_process_check import running_app_skip_reasons

    def _fn(dictionary_names):
        return running_app_skip_reasons(dictionary_names, settings=settings)

    return _fn


def runtime_identity_matches(
    preview_identity: RuntimeIdentity,
    execution_identity: RuntimeIdentity,
) -> bool:
    return preview_identity == execution_identity
