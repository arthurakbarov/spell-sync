"""Validate spell-sync.toml files."""

from __future__ import annotations

from . import settings
from .cli_options import CliOptions
from .command_helpers import quiet_json_output
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .paths import resolve_wordlist_path
from .project import ProjectContext


def cmd_config_check(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        log.section("config check: validate spell-sync.toml")
        project = ProjectContext.build(resolve_wordlist_path(opts.wordlist))
        loaded, issues = settings.load_user_settings_with_issues(
            wordlist=project.wordlist,
            reload=True,
        )
        unknown = settings.unknown_config_keys(loaded)
        paths = [str(path) for path in project.config_paths if path.is_file()]
        ok = not issues and not unknown
        exit_code = ExitCode.OK if ok else ExitCode.LINT_FAILED

        if opts.json_output:
            emit_json(
                {
                    **base_payload("config-check", exit=int(exit_code)),
                    "ok": ok,
                    "paths": paths,
                    "issues": list(issues),
                    "unknown": list(unknown),
                }
            )
            return int(exit_code)

        if not paths:
            log.warn("no spell-sync.toml found (checked user and project paths)")
        else:
            for path in paths:
                log.detail(path)
        for issue in issues:
            log.warn(issue)
        for item in unknown:
            log.warn(item)
        if ok:
            log.done("config check: spell-sync.toml is valid")
        else:
            log.error("config check: fix issues above before relying on settings")
        return int(exit_code)
