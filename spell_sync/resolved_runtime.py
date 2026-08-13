"""Construct resolved runtime types."""

from dataclasses import dataclass
from pathlib import Path

from .push_journal import JournalLoadResult
from .runtime_identity import RuntimeIdentity
from .settings import ConfigLoadResult
from .sync_context import RuntimeContext


class ProjectRuntimeMismatchError(RuntimeError):
    """Bound runtime does not match the requested project."""


@dataclass(frozen=True, slots=True)
class ResolvedRuntime:
    context: RuntimeContext
    config_result: ConfigLoadResult
    journal_result: JournalLoadResult
    identity: RuntimeIdentity

    def assert_wordlist(self, wordlist: Path) -> None:
        if self.context.wordlist.resolve() != wordlist.resolve():
            raise ProjectRuntimeMismatchError(
                "bound runtime wordlist does not match requested project"
            )
