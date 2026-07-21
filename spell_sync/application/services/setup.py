"""Project setup and init orchestration."""

from __future__ import annotations

from pathlib import Path

from ...application.project_resolution import resolve_project_wordlist
from ...project_setup.discovery import SetupTargetDiscovery, discover_setup_targets
from ...project_setup.draft import SetupDraft
from ...project_setup.execute import ProjectSetupExecution, execute_project_setup
from ...project_setup.prepare import PreparedProjectSetup, prepare_project_setup
from ...project_setup.state import ProjectSetupState, inspect_project_setup, validate_setup_wordlist
from ..events import EventLevel, EventSink, OperationEvent, OperationKind
from ..requests import SetupRequest
from ._shared import emit
from .context import ApplicationContext


class SetupService:
    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def inspect_project_setup(self, request: SetupRequest) -> ProjectSetupState:
        return inspect_project_setup(
            resolve_project_wordlist(request.project),
            allow_project_creation=request.allow_project_creation,
        )

    def discover_setup_targets(self, draft: SetupDraft) -> SetupTargetDiscovery:
        return discover_setup_targets(selected_targets=draft.selected_targets)

    def prepare_project_setup(self, draft: SetupDraft) -> PreparedProjectSetup:
        return prepare_project_setup(draft)

    def execute_project_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        confirmed_setup_id: str,
        event_sink: EventSink | None = None,
    ) -> ProjectSetupExecution:
        def _sink(stage: str, message: str) -> None:
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.SETUP,
                    stage,
                    message,
                    level=EventLevel.SUCCESS if stage == "completed" else EventLevel.INFO,
                ),
            )

        return execute_project_setup(
            prepared,
            confirmed_setup_id=confirmed_setup_id,
            event_sink=_sink if event_sink is not None else None,
        )

    def validate_setup_wordlist(self, raw_path: str) -> tuple[Path, str | None]:
        return validate_setup_wordlist(raw_path)
