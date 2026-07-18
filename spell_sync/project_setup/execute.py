"""Atomic project setup execution with rollback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from ..io import atomic_write
from ..operation_lock import OperationLocked, acquire_operation_lock
from ..push_journal import file_content_hash
from ..settings import ConfigStatus, load_config_result
from .prepare import PreparedProjectSetup, SetupFileAction


class ProjectSetupOutcome(str, Enum):
    COMPLETED = "completed"
    STOPPED_SAFELY = "stopped_safely"
    SETUP_INCOMPLETE = "setup_incomplete"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectSetupExecution:
    prepared: PreparedProjectSetup
    outcome: ProjectSetupOutcome
    message: str
    created_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


EventSink = Callable[[str, str], None]


def _fingerprint_matches(path: Path, fingerprint: str | None) -> bool:
    if fingerprint is None:
        return not path.is_file()
    current = file_content_hash(path)
    return current == fingerprint


def execute_project_setup(
    prepared: PreparedProjectSetup,
    *,
    confirmed_setup_id: str,
    event_sink: EventSink | None = None,
) -> ProjectSetupExecution:
    def emit(stage: str, message: str) -> None:
        if event_sink is not None:
            event_sink(stage, message)

    if confirmed_setup_id != prepared.setup_id:
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.FAILED,
            message="Setup confirmation does not match the current preview.",
        )
    if not prepared.can_execute:
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.STOPPED_SAFELY,
            message="Setup preview has conflicts and cannot execute.",
        )

    emit("validating_paths", "Validating setup paths")
    for item in prepared.files:
        if item.action is SetupFileAction.CONFLICT:
            return ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                message=f"Conflict detected: {item.relative_name}",
            )
        if item.action is SetupFileAction.KEEP and item.fingerprint is not None:
            if not _fingerprint_matches(item.path, item.fingerprint):
                return ProjectSetupExecution(
                    prepared=prepared,
                    outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                    message=f"{item.relative_name} changed after preview.",
                )
        if item.action is SetupFileAction.CREATE and item.path.exists():
            return ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.STOPPED_SAFELY,
                message=f"{item.relative_name} appeared after preview.",
            )

    created: list[Path] = []
    try:
        emit("acquiring_lock", "Acquiring project lock")
        with acquire_operation_lock(prepared.wordlist_path, "setup"):
            emit("checking_conflicts", "Checking setup conflicts")
            for directory in prepared.directories_to_create:
                emit("creating_directory", f"Creating {directory.name}")
                if not directory.is_dir():
                    directory.mkdir(parents=True, exist_ok=False)

            for item in prepared.files:
                if item.action is not SetupFileAction.CREATE:
                    continue
                if item.path.name.endswith(".toml"):
                    emit("creating_configuration", f"Writing {item.relative_name}")
                elif "whitelist" in item.relative_name:
                    emit("creating_whitelist", f"Writing {item.relative_name}")
                else:
                    emit("creating_wordlist", f"Writing {item.relative_name}")
                assert item.content is not None
                atomic_write(item.path, item.content, keep_backup=False)
                created.append(item.path)

            emit("verifying_project", "Verifying project files")
            config_result = load_config_result(wordlist=prepared.wordlist_path, reload=True)
            if config_result.status not in (ConfigStatus.VALID, ConfigStatus.UNKNOWN_KEY):
                raise RuntimeError("Created configuration failed validation.")
    except OperationLocked:
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.FAILED,
            message="Another spell-sync process holds the project lock.",
        )
    except FileExistsError as exc:
        _rollback_created(created)
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.STOPPED_SAFELY,
            message=str(exc),
        )
    except OSError as exc:
        incomplete = _rollback_created(created)
        outcome = ProjectSetupOutcome.SETUP_INCOMPLETE if incomplete else ProjectSetupOutcome.FAILED
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=outcome,
            message=str(exc),
            created_files=tuple(path.name for path in created),
        )
    except RuntimeError as exc:
        incomplete = _rollback_created(created)
        outcome = ProjectSetupOutcome.SETUP_INCOMPLETE if incomplete else ProjectSetupOutcome.FAILED
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=outcome,
            message=str(exc),
            created_files=tuple(path.name for path in created),
        )

    emit("completed", "Project setup completed")
    message = (
        "Project created. The existing canonical wordlist was kept unchanged."
        if prepared.existing_wordlist_kept
        else "Project created."
    )
    return ProjectSetupExecution(
        prepared=prepared,
        outcome=ProjectSetupOutcome.COMPLETED,
        message=message,
        created_files=tuple(path.name for path in created),
        warnings=prepared.warnings,
    )


def _rollback_created(paths: list[Path]) -> bool:
    leftover = False
    for path in reversed(paths):
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
        except OSError:
            leftover = True
    return leftover
