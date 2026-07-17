"""CLI command options."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliOptions:
    verbose: bool = False
    dry_run: bool = False
    yes: bool = False
    json_output: bool = False
    fix: bool = False
    strict: bool = False
    wordlist: str | None = None
    add_from: str | None = None
    review_removals: bool = False
    health_check: bool = False
    discard_corrupt_journal: bool = False
    show_targets: bool = False
    plan_removals: bool = False

    @classmethod
    def from_namespace(cls, args: object) -> CliOptions:
        return cls(
            verbose=getattr(args, "verbose", False),
            dry_run=getattr(args, "dry_run", False),
            yes=getattr(args, "yes", False),
            json_output=getattr(args, "json_output", False),
            fix=getattr(args, "fix", False),
            strict=getattr(args, "strict", False),
            wordlist=getattr(args, "wordlist", None),
            add_from=getattr(args, "add_from", None),
            review_removals=getattr(args, "review_removals", False),
            health_check=getattr(args, "health_check", False),
            discard_corrupt_journal=getattr(args, "discard_corrupt_journal", False),
            show_targets=getattr(args, "show_targets", False),
            plan_removals=getattr(args, "plan_removals", False),
        )
