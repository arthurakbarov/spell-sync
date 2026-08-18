"""CLI command options — parser DTO only; map to application requests via cli_request_adapter."""

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
    add_words: tuple[str, ...] = ()
    review_removals: bool = False
    health_check: bool = False
    discard_corrupt_journal: bool = False
    show_targets: bool = False
    plan_removals: bool = False
    support_report_format: str = "text"
    support_report_output: str | None = None
    push_remote: bool = False
    git_message: str | None = None

    @classmethod
    def from_namespace(cls, args: object) -> CliOptions:
        data = vars(args)
        raw_words = data.get("add_words") or ()
        wordlist = data.get("wordlist")
        add_from = data.get("add_from")
        support_output = data.get("support_report_output")
        git_message = data.get("git_message")
        return cls(
            verbose=bool(data.get("verbose", False)),
            dry_run=bool(data.get("dry_run", False)),
            yes=bool(data.get("yes", False)),
            json_output=bool(data.get("json_output", False)),
            fix=bool(data.get("fix", False)),
            strict=bool(data.get("strict", False)),
            wordlist=wordlist if isinstance(wordlist, str) else None,
            add_from=add_from if isinstance(add_from, str) else None,
            add_words=tuple(str(word) for word in raw_words),
            review_removals=bool(data.get("review_removals", False)),
            health_check=bool(data.get("health_check", False)),
            discard_corrupt_journal=bool(data.get("discard_corrupt_journal", False)),
            show_targets=bool(data.get("show_targets", False)),
            plan_removals=bool(data.get("plan_removals", False)),
            support_report_format=str(data.get("support_report_format") or "text"),
            support_report_output=support_output if isinstance(support_output, str) else None,
            push_remote=bool(data.get("push_remote", False)),
            git_message=git_message if isinstance(git_message, str) else None,
        )
