"""Project paths derived from the effective wordlist."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .settings import config_paths_for_wordlist


@dataclass(frozen=True)
class ProjectContext:
    """Canonical project paths for one command."""

    wordlist: Path
    project_dir: Path
    config_paths: tuple[Path, ...]

    @classmethod
    def build(cls, wordlist: Path | str) -> ProjectContext:
        effective_wordlist = Path(wordlist)
        return cls(
            wordlist=effective_wordlist,
            project_dir=effective_wordlist.resolve().parent,
            config_paths=tuple(config_paths_for_wordlist(effective_wordlist)),
        )
