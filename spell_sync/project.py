"""Project paths derived from the effective wordlist."""

from dataclasses import dataclass
from pathlib import Path

from . import settings


@dataclass(frozen=True)
class ProjectContext:
    """Canonical project paths for one command."""

    wordlist: Path
    project_dir: Path
    config_path: Path

    @classmethod
    def build(cls, wordlist: Path | str) -> ProjectContext:
        effective_wordlist = Path(wordlist)
        return cls(
            wordlist=effective_wordlist,
            project_dir=effective_wordlist.resolve().parent,
            config_path=settings.project_config_path(effective_wordlist),
        )
