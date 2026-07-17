"""CLI wiring helpers for invariant tests."""

from __future__ import annotations

import argparse

import spell_sync.cli as cli_mod


def cli_subcommand_names() -> set[str]:
    parser = cli_mod._build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("CLI parser has no subcommands")
