"""Prepare immutable project setup plans."""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..bundled_files import bundled_path
from ..config import WHITELIST_FILENAME
from ..guest_messages import SETUP_WORD_LIST_MISSING, SETUP_WORD_LIST_UNREADABLE
from ..io import wordlist_unreadable
from ..push_journal import file_content_hash
from .discovery import config_draft_from_targets
from .draft import ProjectConfigDraft, SetupDraft
from .render import render_project_config


class SetupFileAction(StrEnum):
    CREATE = "create"
    KEEP = "keep"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class PlannedSetupFile:
    action: SetupFileAction
    path: Path
    relative_name: str
    content: bytes | None
    fingerprint: str | None = None


@dataclass(frozen=True)
class PreparedProjectSetup:
    setup_id: str
    project_dir: Path
    wordlist_path: Path
    config_path: Path
    whitelist_path: Path
    directories_to_create: tuple[Path, ...]
    files: tuple[PlannedSetupFile, ...]
    selected_target_ids: tuple[str, ...]
    enabled_targets: tuple[str, ...]
    warnings: tuple[str, ...]
    conflicts: tuple[str, ...]
    can_execute: bool
    existing_wordlist_kept: bool
    config_draft: ProjectConfigDraft


def _empty_wordlist_bytes() -> bytes:
    return b""


def _whitelist_bytes() -> bytes:
    return bundled_path("lint-whitelist.txt").read_bytes()


def _setup_fingerprint(files: tuple[PlannedSetupFile, ...], enabled: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.action.value.encode("utf-8"))
        digest.update(str(item.path).encode("utf-8"))
        digest.update((item.fingerprint or "").encode("utf-8"))
        digest.update(item.content or b"")
    for target in enabled:
        digest.update(target.encode("utf-8"))
    return digest.hexdigest()[:16]


def prepare_project_setup(draft: SetupDraft) -> PreparedProjectSetup:
    wordlist_path = draft.wordlist_path
    project_dir = wordlist_path.parent
    config_path = project_dir / "spell-sync.toml"
    whitelist_path = project_dir / WHITELIST_FILENAME
    config_draft = config_draft_from_targets(
        draft.selected_targets,
        excluded_dictionaries=draft.excluded_dictionaries,
    )

    files: list[PlannedSetupFile] = []
    conflicts: list[str] = []
    warnings: list[str] = []
    existing_wordlist_kept = False

    if wordlist_path.is_file():
        if wordlist_unreadable(wordlist_path):
            files.append(
                PlannedSetupFile(
                    action=SetupFileAction.CONFLICT,
                    path=wordlist_path,
                    relative_name=wordlist_path.name,
                    content=None,
                )
            )
            conflicts.append(SETUP_WORD_LIST_UNREADABLE)
        else:
            fingerprint = file_content_hash(wordlist_path)
            files.append(
                PlannedSetupFile(
                    action=SetupFileAction.KEEP,
                    path=wordlist_path,
                    relative_name=wordlist_path.name,
                    content=None,
                    fingerprint=fingerprint,
                )
            )
            existing_wordlist_kept = True
    elif draft.create_wordlist:
        if wordlist_path.exists():
            files.append(
                PlannedSetupFile(
                    action=SetupFileAction.CONFLICT,
                    path=wordlist_path,
                    relative_name=wordlist_path.name,
                    content=None,
                )
            )
            conflicts.append(
                f"{wordlist_path.name} exists but is not a regular file.",
            )
        else:
            files.append(
                PlannedSetupFile(
                    action=SetupFileAction.CREATE,
                    path=wordlist_path,
                    relative_name=wordlist_path.name,
                    content=_empty_wordlist_bytes(),
                )
            )
    else:
        conflicts.append(SETUP_WORD_LIST_MISSING)

    if config_path.is_file():
        files.append(
            PlannedSetupFile(
                action=SetupFileAction.CONFLICT,
                path=config_path,
                relative_name=config_path.name,
                content=None,
                fingerprint=file_content_hash(config_path),
            )
        )
        conflicts.append("spell-sync.toml already exists.")
    else:
        files.append(
            PlannedSetupFile(
                action=SetupFileAction.CREATE,
                path=config_path,
                relative_name=config_path.name,
                content=render_project_config(config_draft),
            )
        )

    if whitelist_path.is_file():
        files.append(
            PlannedSetupFile(
                action=SetupFileAction.KEEP,
                path=whitelist_path,
                relative_name=whitelist_path.name,
                content=None,
                fingerprint=file_content_hash(whitelist_path),
            )
        )
    else:
        files.append(
            PlannedSetupFile(
                action=SetupFileAction.CREATE,
                path=whitelist_path,
                relative_name=whitelist_path.name,
                content=_whitelist_bytes(),
            )
        )

    directories = (project_dir,) if not project_dir.exists() else ()
    file_tuple = tuple(files)
    setup_id = _setup_fingerprint(file_tuple, draft.selected_targets)
    can_execute = not conflicts and all(
        item.action in {SetupFileAction.CREATE, SetupFileAction.KEEP} for item in file_tuple
    )
    return PreparedProjectSetup(
        setup_id=setup_id,
        project_dir=project_dir,
        wordlist_path=wordlist_path,
        config_path=config_path,
        whitelist_path=whitelist_path,
        directories_to_create=directories,
        files=file_tuple,
        selected_target_ids=draft.selected_targets,
        enabled_targets=config_draft.enabled_targets,
        warnings=tuple(warnings),
        conflicts=tuple(conflicts),
        can_execute=can_execute,
        existing_wordlist_kept=existing_wordlist_kept,
        config_draft=config_draft,
    )
