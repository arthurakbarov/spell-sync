"""In-memory setup draft types."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SetupDraft:
    wordlist_path: Path
    selected_targets: tuple[str, ...]
    create_wordlist: bool
    excluded_dictionaries: tuple[str, ...] = ()


@dataclass(frozen=True)
class SafetyConfig:
    backup_keep: int = 3


@dataclass(frozen=True)
class ProjectConfigDraft:
    schema_version: int
    enabled_targets: tuple[str, ...]
    safety: SafetyConfig
    # Exact dictionary names excluded while their family remains enabled.
    excluded_dictionaries: tuple[str, ...] = ()
