"""Project setup state inspection and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..io import wordlist_unreadable
from ..project import ProjectContext
from ..push_journal import JournalLoadStatus, load_journal_result
from ..read_outcome import ReadStatus
from ..settings import ConfigStatus, config_blocks_mutating, load_config_result


class ProjectSetupStatus(str, Enum):
    READY = "ready"
    MISSING_WORDLIST = "missing_wordlist"
    MISSING_CONFIG = "missing_config"
    MISSING_PROJECT = "missing_project"
    INVALID_CONFIG = "invalid_config"
    UNREADABLE_WORDLIST = "unreadable_wordlist"
    RECOVERY_REQUIRED = "recovery_required"
    AMBIGUOUS_PROJECT = "ambiguous_project"


@dataclass(frozen=True)
class ProjectSetupDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ProjectSetupState:
    status: ProjectSetupStatus
    effective_wordlist: Path | None
    project_dir: Path | None
    config_path: Path | None
    can_start_wizard: bool
    detail: str | None
    diagnostics: tuple[ProjectSetupDiagnostic, ...] = ()


def _blocking_journal_status(journal_status: JournalLoadStatus) -> bool:
    return journal_status not in (
        JournalLoadStatus.ABSENT,
        JournalLoadStatus.VALID_COMPLETED,
    )


def inspect_project_setup(
    wordlist: Path,
    *,
    allow_project_creation: bool = True,
) -> ProjectSetupState:
    project = ProjectContext.build(wordlist)
    project_dir = project.project_dir
    config_path = project_dir / "spell-sync.toml"
    diagnostics: list[ProjectSetupDiagnostic] = []

    journal_result = load_journal_result(wordlist, validate_wordlist=False)
    if _blocking_journal_status(journal_result.status):
        detail = journal_result.detail or journal_result.status.value
        diagnostics.append(
            ProjectSetupDiagnostic(
                code="recovery_required",
                message=f"Unfinished recovery journal: {detail}",
            )
        )
        return ProjectSetupState(
            status=ProjectSetupStatus.RECOVERY_REQUIRED,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=config_path if config_path.is_file() else None,
            can_start_wizard=False,
            detail="Resolve recovery before creating or changing the project.",
            diagnostics=tuple(diagnostics),
        )

    config_result = load_config_result(wordlist=wordlist, reload=True)
    project_config = config_path
    home_config = project.config_paths[0] if project.config_paths else None
    if (
        project_config.is_file()
        and home_config is not None
        and home_config.is_file()
        and home_config.resolve() != project_config.resolve()
        and config_result.status is not ConfigStatus.ABSENT
    ):
        diagnostics.append(
            ProjectSetupDiagnostic(
                code="ambiguous_project",
                message="Both user and project spell-sync.toml are present.",
            )
        )
        return ProjectSetupState(
            status=ProjectSetupStatus.AMBIGUOUS_PROJECT,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=config_path,
            can_start_wizard=False,
            detail="Resolve ambiguous configuration before continuing.",
            diagnostics=tuple(diagnostics),
        )

    if config_result.status is not ConfigStatus.ABSENT and config_blocks_mutating(config_result):
        diagnostics.append(
            ProjectSetupDiagnostic(
                code="invalid_config",
                message=config_result.diagnostics[0].message
                if config_result.diagnostics
                else config_result.status.value,
            )
        )
        return ProjectSetupState(
            status=ProjectSetupStatus.INVALID_CONFIG,
            effective_wordlist=wordlist if wordlist.is_file() else None,
            project_dir=project_dir,
            config_path=config_path if config_path.is_file() else None,
            can_start_wizard=False,
            detail="Fix spell-sync.toml before using the setup wizard.",
            diagnostics=tuple(diagnostics),
        )

    wordlist_exists = wordlist.is_file()
    config_exists = config_path.is_file()

    if wordlist_exists and wordlist_unreadable(wordlist):
        return ProjectSetupState(
            status=ProjectSetupStatus.UNREADABLE_WORDLIST,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=config_path if config_exists else None,
            can_start_wizard=False,
            detail="The canonical wordlist exists but cannot be read safely.",
            diagnostics=(
                ProjectSetupDiagnostic(
                    code="unreadable_wordlist",
                    message="Choose another wordlist path or fix permissions.",
                ),
            ),
        )

    if wordlist_exists and not config_exists:
        return ProjectSetupState(
            status=ProjectSetupStatus.MISSING_CONFIG,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=None,
            can_start_wizard=False,
            detail="Configuration is missing next to the existing wordlist.",
            diagnostics=(
                ProjectSetupDiagnostic(
                    code="missing_config",
                    message="Create spell-sync.toml manually or use spell-sync init.",
                ),
            ),
        )

    if config_exists and not wordlist_exists:
        return ProjectSetupState(
            status=ProjectSetupStatus.MISSING_WORDLIST,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=config_path,
            can_start_wizard=False,
            detail="Configuration exists but the canonical wordlist is missing.",
            diagnostics=(
                ProjectSetupDiagnostic(
                    code="missing_wordlist",
                    message="Restore wordlist.txt or choose a different project path.",
                ),
            ),
        )

    if not wordlist_exists and not config_exists:
        can_wizard = allow_project_creation
        return ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=None,
            can_start_wizard=can_wizard,
            detail="No Spell Sync project was found.",
            diagnostics=(),
        )

    if (
        wordlist_exists
        and config_exists
        and config_result.status
        in (
            ConfigStatus.VALID,
            ConfigStatus.UNKNOWN_KEY,
        )
    ):
        return ProjectSetupState(
            status=ProjectSetupStatus.READY,
            effective_wordlist=wordlist,
            project_dir=project_dir,
            config_path=config_path,
            can_start_wizard=False,
            detail=None,
            diagnostics=(),
        )

    return ProjectSetupState(
        status=ProjectSetupStatus.MISSING_PROJECT,
        effective_wordlist=wordlist,
        project_dir=project_dir,
        config_path=config_path if config_exists else None,
        can_start_wizard=False,
        detail="Project state could not be determined safely.",
        diagnostics=tuple(diagnostics),
    )


def normalize_wordlist_input(raw: str) -> Path:
    text = raw.strip()
    if not text:
        raise ValueError("Wordlist path is required.")
    path = Path(text).expanduser()
    if path.exists() and path.is_dir():
        raise ValueError("Wordlist path must be a file, not a directory.")
    if path.name in {"", ".", ".."}:
        raise ValueError("Wordlist filename is required.")
    parent = path.parent
    if parent.exists() and parent.is_file():
        raise ValueError("Parent path is an existing file.")
    return path.resolve()


def inspect_existing_wordlist(path: Path) -> tuple[int | None, ReadStatus | None, str | None]:
    if not path.is_file():
        return None, None, None
    if wordlist_unreadable(path):
        return None, ReadStatus.UNREADABLE, "Wordlist exists but cannot be read."
    from ..io import read_text_words

    try:
        words = read_text_words(str(path))
    except OSError as exc:
        return None, ReadStatus.UNREADABLE, str(exc)
    return len(words), ReadStatus.OK, None


def validate_setup_wordlist(raw_path: str) -> tuple[Path, str | None]:
    normalized = normalize_wordlist_input(raw_path)
    project_dir = normalized.parent
    detail_parts = [
        f"Resolved path:\n{normalized}",
        f"Project directory:\n{project_dir}",
    ]
    count, status, error = inspect_existing_wordlist(normalized)
    if status is ReadStatus.UNREADABLE:
        raise ValueError(error or "Wordlist is unreadable.")
    if count is not None:
        detail_parts.append(f"Existing wordlist: {count} words")
    else:
        detail_parts.append("Wordlist will be created on confirmation.")
    config_path = project_dir / "spell-sync.toml"
    if config_path.is_file():
        detail_parts.append(f"Existing config detected: {config_path}")
    return normalized, "\n\n".join(detail_parts)
