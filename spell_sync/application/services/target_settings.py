"""Target settings load and update orchestration."""

from __future__ import annotations

from ...application.project_resolution import resolve_project_wordlist
from ...project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsExecution,
    TargetSettingsSnapshot,
    execute_target_settings_update,
    load_target_settings_snapshot,
    prepare_target_settings_update,
)
from ...push_journal import JournalLoadStatus
from ..events import EventSink
from ..requests import PrepareTargetSettingsUpdateRequest, TargetSettingsRequest
from ._shared import make_operation_emitter
from .context import ApplicationContext


class TargetSettingsService:
    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def load_target_settings(self, request: TargetSettingsRequest) -> TargetSettingsSnapshot:
        return load_target_settings_snapshot(
            wordlist=resolve_project_wordlist(request.project),
        )

    def prepare_target_settings_update(
        self,
        request: PrepareTargetSettingsUpdateRequest,
    ) -> PreparedTargetSettingsUpdate:
        wordlist = resolve_project_wordlist(request.project)
        validated = self._ctx.runtime.validated(request.project)
        pending_recovery = validated.journal_result.status not in (
            JournalLoadStatus.ABSENT,
            JournalLoadStatus.VALID_COMPLETED,
        )
        return prepare_target_settings_update(
            wordlist=wordlist,
            selected_target_ids=request.selected_target_ids,
            pending_recovery=pending_recovery,
        )

    def execute_target_settings_update(
        self,
        prepared: PreparedTargetSettingsUpdate,
        *,
        confirmed_update_id: str,
        event_sink: EventSink | None = None,
    ) -> TargetSettingsExecution:
        emitter = make_operation_emitter(event_sink)
        return execute_target_settings_update(
            prepared,
            confirmed_update_id=confirmed_update_id,
            event_sink=emitter.emit,
        )
