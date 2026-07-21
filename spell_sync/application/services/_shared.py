"""Shared helpers for application services."""

from __future__ import annotations

from ...runtime_identity import RuntimeIdentity
from ..events import PresentationEventSink, TechnicalEvent, operation_emitter

HISTORY_SAVE_WARNING = "Operation completed, but its history record could not be saved."

RUNTIME_CHANGED_MESSAGE = (
    "Project configuration or targets changed after the preview was created. "
    "Request a new preview before executing."
)


def emit_technical(presentation_sink: PresentationEventSink | None, event: TechnicalEvent) -> None:
    operation_emitter(presentation_sink).emit(event)


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
