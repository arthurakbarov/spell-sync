"""CLI entry point."""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict

from .cli_options import CliOptions
from .commands import cmd_init, cmd_lint, cmd_pull, cmd_push, cmd_status
from .config_check_cmd import cmd_config_check
from .doctor import cmd_doctor
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .plan_cmd import cmd_plan
from .recover_cmd import cmd_recover
from .version_cmd import cmd_version

CommandFn = Callable[[CliOptions], int]

COMMANDS: Dict[str, CommandFn] = {
    "config-check": cmd_config_check,
    "doctor": cmd_doctor,
    "init": cmd_init,
    "lint": cmd_lint,
    "plan": cmd_plan,
    "pull": cmd_pull,
    "push": cmd_push,
    "recover": cmd_recover,
    "status": cmd_status,
    "version": cmd_version,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spell-sync",
        description="Unified custom spell-check word list.",
    )
    sub = parser.add_subparsers(dest="command")

    def add_common_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "-C",
            "--wordlist",
            dest="wordlist",
            metavar="PATH",
            help="path to wordlist.txt (default: project root or cwd)",
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
            help="merge words from external UTF-8 or Hunspell file into wordlist",
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

    status_p = sub.add_parser("status", help="wordlist vs dictionary diffs")
    status_p.add_argument("-v", "--verbose", action="store_true")
    add_common_flags(status_p)

    pull_p = sub.add_parser("pull", help="merge dictionary words into wordlist")
    add_pull_flags(pull_p)
    add_common_flags(pull_p)

    push_p = sub.add_parser("push", help="write wordlist to dictionaries")
    add_push_flags(push_p)
    add_common_flags(push_p)

    plan_p = sub.add_parser("plan", help="preview push without writing")
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

    lint_p = sub.add_parser("lint", help="check wordlist.txt quality")
    lint_p.add_argument("--fix", action="store_true")
    lint_p.add_argument("--strict", action="store_true")
    add_common_flags(lint_p)

    recover_p = sub.add_parser(
        "recover",
        help="restore from unfinished push journal (crash recovery)",
    )
    recover_p.add_argument("-n", "--dry-run", dest="dry_run", action="store_true")
    recover_p.add_argument("-y", "--yes", action="store_true")
    recover_p.add_argument(
        "--discard-corrupt-journal",
        dest="discard_corrupt_journal",
        action="store_true",
        help="explicitly remove a corrupt journal without restoring (dangerous)",
    )
    add_common_flags(recover_p)

    init_p = sub.add_parser(
        "init",
        help="create wordlist.txt, spell-sync.toml, and lint-whitelist.txt from bundled examples",
    )
    add_common_flags(init_p)

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
        help="list discovered dictionary paths",
    )
    add_common_flags(doctor_p)

    version_p = sub.add_parser("version", help="print installed package version")
    add_common_flags(version_p)

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
    if argv is None:
        argv = sys.argv
    rest = argv[1:]
    if rest in (["-h"], ["--help"]):
        _build_parser().print_help()
        return int(ExitCode.OK)
    args = _parse_args(rest)
    if args is None:
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
