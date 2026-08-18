"""CLI entry point."""

import argparse
import sys
from collections.abc import Callable

from .application.product_concepts import (
    CLI_ADD_HELP,
    CLI_INIT_HELP,
    CLI_PLAN_HELP,
    CLI_PULL_HELP,
    CLI_PUSH_HELP,
    CLI_PUSH_REDUNDANCY_EPILOG,
    CLI_RECOVER_HELP,
    CLI_ROOT_DESCRIPTION,
    CLI_STATUS_HELP,
)
from .cli_options import CliOptions
from .commands import cmd_add, cmd_init, cmd_lint, cmd_pull, cmd_push, cmd_status
from .config_check_cmd import cmd_config_check
from .doctor import cmd_doctor
from .exit_codes import ExitCode
from .git_save_cmd import cmd_git_save
from .guest_messages import RECOVER_DISCARD_HELP
from .json_output import base_payload, emit_json, reset_json_emission
from .log import log
from .plan_cmd import cmd_plan
from .recover_cmd import cmd_recover
from .support_report_cmd import cmd_support_report
from .tui.routing import (
    print_non_interactive_ui_error,
    print_non_interactive_usage_error,
    should_launch_tui,
)
from .ui_cmd import cmd_ui
from .version_cmd import cmd_version

type CommandFn = Callable[[CliOptions], int]

COMMANDS: dict[str, CommandFn] = {
    "add": cmd_add,
    "config-check": cmd_config_check,
    "doctor": cmd_doctor,
    "git-save": cmd_git_save,
    "init": cmd_init,
    "lint": cmd_lint,
    "plan": cmd_plan,
    "pull": cmd_pull,
    "push": cmd_push,
    "recover": cmd_recover,
    "status": cmd_status,
    "support-report": cmd_support_report,
    "ui": cmd_ui,
    "version": cmd_version,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spell-sync",
        description=CLI_ROOT_DESCRIPTION,
        epilog=CLI_PUSH_REDUNDANCY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    def add_common_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "-C",
            "--wordlist",
            dest="wordlist",
            metavar="PATH",
            help="path to wordlist.txt (default: cwd project, else last opened)",
        )
        subparser.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            help="emit JSON on stdout instead of human-readable log",
        )

    def add_pull_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--add-from",
            dest="add_from",
            metavar="PATH",
            help=(
                "merge words from an external UTF-8 or Hunspell file; "
                "same preview and workspace warnings as a normal pull"
            ),
        )

    def add_push_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("-n", "--dry-run", dest="dry_run", action="store_true")
        subparser.add_argument("-v", "--verbose", action="store_true")
        subparser.add_argument("-y", "--yes", action="store_true")
        subparser.add_argument(
            "--review-removals",
            dest="review_removals",
            action="store_true",
            help="list words push would remove and prompt before writing",
        )
        subparser.add_argument(
            "--strict",
            action="store_true",
            help="abort if any dictionary would be skipped (unreadable, backup fail, etc.)",
        )

    status_p = sub.add_parser("status", help=CLI_STATUS_HELP)
    status_p.add_argument("-v", "--verbose", action="store_true")
    add_common_flags(status_p)

    pull_p = sub.add_parser(
        "pull",
        help=CLI_PULL_HELP,
    )
    add_pull_flags(pull_p)
    add_common_flags(pull_p)

    push_p = sub.add_parser(
        "push",
        help=CLI_PUSH_HELP,
    )
    add_push_flags(push_p)
    add_common_flags(push_p)

    plan_p = sub.add_parser("plan", help=CLI_PLAN_HELP)
    plan_p.add_argument("-v", "--verbose", action="store_true")
    plan_p.add_argument(
        "--removals",
        dest="plan_removals",
        action="store_true",
        help="preview words push would remove",
    )
    plan_p.add_argument(
        "--strict",
        action="store_true",
        help="abort if any dictionary would be skipped (unreadable, backup fail, etc.)",
    )
    add_common_flags(plan_p)

    config_check_p = sub.add_parser(
        "config-check",
        help="validate spell-sync.toml",
    )
    add_common_flags(config_check_p)

    lint_p = sub.add_parser("lint", help="check word list quality")
    lint_p.add_argument("--fix", action="store_true")
    lint_p.add_argument("--strict", action="store_true")
    add_common_flags(lint_p)

    recover_p = sub.add_parser(
        "recover",
        help=CLI_RECOVER_HELP,
    )
    recover_p.add_argument("-n", "--dry-run", dest="dry_run", action="store_true")
    recover_p.add_argument("-y", "--yes", action="store_true")
    recover_p.add_argument(
        "--discard-corrupt-journal",
        dest="discard_corrupt_journal",
        action="store_true",
        help=RECOVER_DISCARD_HELP,
    )
    add_common_flags(recover_p)

    init_p = sub.add_parser(
        "init",
        help=CLI_INIT_HELP,
    )
    add_common_flags(init_p)

    add_p = sub.add_parser("add", help=CLI_ADD_HELP)
    add_p.add_argument(
        "add_words",
        nargs="+",
        metavar="WORD",
        help="personal word(s) to add to your word list",
    )
    add_common_flags(add_p)

    git_save_p = sub.add_parser(
        "git-save",
        help="commit wordlist.txt / spell-sync.toml in a personal Git workspace",
    )
    git_save_p.add_argument(
        "--push",
        dest="push_remote",
        action="store_true",
        help="also push to the configured upstream after commit",
    )
    git_save_p.add_argument(
        "-m",
        "--message",
        dest="git_message",
        metavar="TEXT",
        help="commit message (default: Update personal Spell Sync word list)",
    )
    git_save_p.add_argument("-y", "--yes", action="store_true")
    add_common_flags(git_save_p)

    doctor_p = sub.add_parser("doctor", help="check paths, permissions, and drift")
    doctor_p.add_argument(
        "--check",
        dest="health_check",
        action="store_true",
        help="exit 2 when doctor has required next-step actions; exit 1 on blocking errors",
    )
    doctor_p.add_argument(
        "--targets",
        dest="show_targets",
        action="store_true",
        help="list discovered app dictionary paths",
    )
    add_common_flags(doctor_p)

    version_p = sub.add_parser("version", help="print installed package version")
    add_common_flags(version_p)

    support_p = sub.add_parser(
        "support-report",
        help="export a redacted diagnostic support report",
    )
    support_p.add_argument(
        "--format",
        dest="support_report_format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    support_p.add_argument(
        "--output",
        dest="support_report_output",
        metavar="PATH",
        help="write report to PATH instead of the default support-reports directory",
    )
    add_common_flags(support_p)

    ui_p = sub.add_parser("ui", help="open interactive TUI dashboard")
    ui_p.add_argument(
        "-C",
        "--wordlist",
        dest="wordlist",
        metavar="PATH",
        help="path to wordlist.txt (default: cwd project, else last opened)",
    )

    return parser


def _parse_args(argv: list[str]) -> argparse.Namespace | None:
    defaults = {
        "command": "status",
        "verbose": False,
        "dry_run": False,
        "yes": False,
        "json_output": False,
        "fix": False,
        "strict": False,
        "wordlist": None,
        "add_from": None,
        "review_removals": False,
        "health_check": False,
        "discard_corrupt_journal": False,
        "show_targets": False,
        "plan_removals": False,
        "support_report_format": "text",
        "support_report_output": None,
    }
    if not argv:
        return argparse.Namespace(**defaults)
    if argv[0] not in COMMANDS:
        if argv[0].startswith("-"):
            argv = ["status", *argv]
        else:
            return None
    parser = _build_parser()
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    reset_json_emission()
    if argv is None:
        argv = sys.argv
    rest = argv[1:]
    if rest in (["-h"], ["--help"]):
        _build_parser().print_help()
        return int(ExitCode.OK)
    if rest == ["--version"]:
        return cmd_version(CliOptions())
    if not rest:
        if should_launch_tui(
            None,
            stdin_is_tty=sys.stdin.isatty(),
            stdout_is_tty=sys.stdout.isatty(),
            json_requested=False,
        ):
            return cmd_ui(CliOptions())
        print_non_interactive_usage_error()
        return int(ExitCode.LINT_FAILED)
    if rest[0] == "ui" and "--json" in rest:
        log.error("unrecognized arguments: --json")
        log.info("Run `spell-sync ui --help` for usage.")
        return int(ExitCode.LINT_FAILED)
    if rest[0] == "ui" and not should_launch_tui(
        "ui",
        stdin_is_tty=sys.stdin.isatty(),
        stdout_is_tty=sys.stdout.isatty(),
        json_requested=False,
    ):
        print_non_interactive_ui_error()
        return int(ExitCode.LINT_FAILED)
    parsed = _parse_args(rest)
    if parsed is None:
        unknown = rest[0] if rest else ""
        if "--json" in rest:
            emit_json(
                {
                    **base_payload("cli", exit=int(ExitCode.UNKNOWN_COMMAND)),
                    "error": "unknown_command",
                    "unknown": unknown,
                    "argv": rest,
                }
            )
            return int(ExitCode.UNKNOWN_COMMAND)
        log.error(f"unknown command: {unknown}")
        log.info("Run `spell-sync --help` for usage.")
        return int(ExitCode.UNKNOWN_COMMAND)

    args = parsed
    command = args.command or "status"
    opts = CliOptions.from_namespace(args)
    was_quiet = log.quiet
    if opts.json_output:
        log.quiet = True

    try:
        return COMMANDS[command](opts)
    finally:
        log.quiet = was_quiet


def entry_point() -> None:
    """Entry point for console_scripts (pip install)."""
    raise SystemExit(main(sys.argv))
