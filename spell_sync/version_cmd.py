"""version: print installed package version."""

from __future__ import annotations

from .cli_options import CliOptions
from .command_helpers import emit_command_exit
from .exit_codes import ExitCode
from .runtime import installed_package_version


def cmd_version(opts: CliOptions) -> int:
    installed = installed_package_version()
    if opts.json_output:
        return emit_command_exit(opts, "version", ExitCode.OK, version=installed)
    print(installed)
    return int(ExitCode.OK)
