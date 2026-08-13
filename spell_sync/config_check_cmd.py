"""Validate spell-sync.toml."""

from . import settings
from .cli_options import CliOptions
from .command_helpers import quiet_json_output
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .operation_presenter import OperationSpec, operation_session
from .paths import resolve_wordlist_path
from .project import ProjectContext


def cmd_config_check(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with operation_session(
            OperationSpec(
                key="config-check",
                title="config check: validate spell-sync.toml",
                descriptions=("Validate local Spell Sync configuration file.",),
                activity="Config check",
            ),
            enabled=not opts.json_output,
        ) as session:
            project = ProjectContext.build(resolve_wordlist_path(opts.wordlist))
            loaded, issues = settings.load_project_settings_with_issues(
                wordlist=project.wordlist,
            )
            unknown = settings.unknown_config_keys(loaded)
            path = str(project.config_path) if project.config_path.is_file() else None
            ok = not issues and not unknown
            exit_code = ExitCode.OK if ok else ExitCode.LINT_FAILED

            if opts.json_output:
                emit_json(
                    {
                        **base_payload("config-check", exit=int(exit_code)),
                        "ok": ok,
                        "path": path,
                        "issues": list(issues),
                        "unknown": list(unknown),
                    }
                )
                return int(exit_code)

            if path is None:
                log.warn("no spell-sync.toml found beside the wordlist")
            else:
                log.detail(path)
            for issue in issues:
                log.warn(issue)
            for item in unknown:
                log.warn(item)
            if ok:
                if session is not None:
                    session.succeed("config check: spell-sync.toml is valid")
                else:
                    log.done("config check: spell-sync.toml is valid")
            elif session is not None:
                session.fail("config check: fix issues above before relying on settings")
            else:
                log.error("config check: fix issues above before relying on settings")
            return int(exit_code)
